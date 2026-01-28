import re
import httpx
from typing import Optional, Tuple, List, Union, Dict, Any
from datetime import datetime
import logging
import email.utils
import xml.etree.ElementTree as ET

from shared.arxiv.models import (
    ParsedArxivUrl,
    NormalizedArxivId,
    ArxivMetadata,
    ArxivAuthor,
    ArxivVersion,
    ArxivPdfHead,
    ArxivPdfResult,
    ArxivPdfForProcessing,
)
from shared.utils import to_epoch_seconds
import os


logger = logging.getLogger(__name__)

# Endpoints and networking defaults
ARXIV_HOST = "https://arxiv.org"
ARXIV_EXPORT_HOST = "http://export.arxiv.org"
TIMEOUT_SECONDS = 60
DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1 (+https://arxiv.org)",
}


# --- Helpers: ID parsing / normalization ---

_NEW_STYLE_RE = re.compile(r"^(?P<id>\d{4}\.\d{4,5})(?P<ver>v\d+)?$")
_OLD_STYLE_RE = re.compile(r"^(?P<id>[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?P<ver>v\d+)?$", re.IGNORECASE)


def _split_id_and_version(id_or_versioned: str) -> Tuple[str, Optional[str]]:
    m = _NEW_STYLE_RE.match(id_or_versioned)
    if m:
        return m.group("id"), m.group("ver")
    m = _OLD_STYLE_RE.match(id_or_versioned)
    if m:
        return m.group("id"), m.group("ver")
    # If user passed something like 1234.56789v2.pdf or with .pdf suffix, strip it and retry
    cleaned = id_or_versioned.strip()
    if cleaned.endswith(".pdf"):
        cleaned = cleaned[:-4]
    if cleaned.lower().startswith("arxiv:"):
        cleaned = cleaned.split(":", 1)[1]
    # One more attempt after cleaning
    m = _NEW_STYLE_RE.match(cleaned) or _OLD_STYLE_RE.match(cleaned)
    if m:
        return m.group("id"), m.group("ver")
    raise ValueError(f"Unrecognized arXiv identifier: {id_or_versioned}")


async def parse_url(url: str) -> ParsedArxivUrl:
    """Parse an arXiv URL or identifier into components."""
    raw = url.strip()
    # Accept raw IDs / arXiv:ID
    if not raw.startswith("http://") and not raw.startswith("https://"):
        arxiv_id, version = _split_id_and_version(raw)
        return ParsedArxivUrl(raw=raw, arxiv_id=arxiv_id, version=version, url_type="id")

    # Normalize hostname and path
    m = re.match(r"^https?://[^/]+/(.+)$", raw)
    if not m:
        raise ValueError("Invalid arXiv URL")
    path = m.group(1)

    # Match /abs/<id>(vN)[optional slash] with optional query/fragment
    abs_m = re.match(r"^abs/(?P<idver>[^/?#]+)(?:/)?(?:[?#].*)?$", path)
    if abs_m:
        idver = abs_m.group("idver")
        arxiv_id, version = _split_id_and_version(idver)
        return ParsedArxivUrl(raw=raw, arxiv_id=arxiv_id, version=version, url_type="abs")

    # Match /pdf/<id>(vN)[.pdf optional][optional slash] with optional query/fragment
    pdf_m = re.match(r"^pdf/(?P<idver>[^/?#]+?)(?:\.pdf)?(?:/)?(?:[?#].*)?$", path)
    if pdf_m:
        idver = pdf_m.group("idver")
        arxiv_id, version = _split_id_and_version(idver)
        return ParsedArxivUrl(raw=raw, arxiv_id=arxiv_id, version=version, url_type="pdf")

    raise ValueError("Unsupported arXiv URL format")


async def normalize_id(id_or_url: str) -> NormalizedArxivId:
    """Return canonical arXiv id and optional version from a URL or ID string."""
    try:
        parsed = await parse_url(id_or_url)
        return NormalizedArxivId(arxiv_id=parsed.arxiv_id, version=parsed.version)
    except ValueError:
        arxiv_id, version = _split_id_and_version(id_or_url)
        return NormalizedArxivId(arxiv_id=arxiv_id, version=version)


def build_pdf_url(arxiv_id: str, version: Optional[str] = None) -> str:
    suffix = version or ""
    return f"{ARXIV_HOST}/pdf/{arxiv_id}{suffix}.pdf"


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True)


def _parse_rfc2822_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        ts = email.utils.parsedate_to_datetime(value)
        return ts
    except Exception:
        return None


def _find_text(elem: ET.Element, tag: str) -> Optional[str]:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    found = elem.find(tag, ns)
    return found.text.strip() if found is not None and found.text else None


async def fetch_metadata(arxiv_id: str) -> ArxivMetadata:
    """Fetch metadata from arXiv Atom API for a single identifier."""
    query_url = f"{ARXIV_EXPORT_HOST}/api/query?id_list={arxiv_id}"
    async with _http_client() as client:
        resp = await client.get(query_url)
        resp.raise_for_status()
        content = resp.content

    # Parse Atom XML
    root = ET.fromstring(content)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ValueError(f"No metadata found for {arxiv_id}")

    title = _find_text(entry, "atom:title") or ""
    summary = _find_text(entry, "atom:summary") or ""
    doi = _find_text(entry, "arxiv:doi")
    journal_ref = _find_text(entry, "arxiv:journal_ref")
    updated_str = _find_text(entry, "atom:updated")
    published_str = _find_text(entry, "atom:published")

    # Authors
    authors: List[ArxivAuthor] = []
    for a in entry.findall("atom:author", ns):
        name = _find_text(a, "atom:name") or ""
        affiliation = _find_text(a, "arxiv:affiliation")
        authors.append(ArxivAuthor(name=name, affiliation=affiliation))

    # Categories
    categories = [c.attrib.get("term", "") for c in entry.findall("atom:category", ns) if c.attrib.get("term")]

    # Versions
    versions: List[ArxivVersion] = []
    for v in entry.findall("arxiv:version", ns):
        ver = v.attrib.get("version") or (v.text.strip() if v.text else None)
        dt = _parse_rfc2822_date(v.attrib.get("updated")) or _parse_rfc2822_date(v.text)
        if ver:
            versions.append(ArxivVersion(version=ver, updated_at=dt))

    latest_version = versions[-1].version if versions else None

    return ArxivMetadata(
        arxiv_id=arxiv_id,
        latest_version=latest_version,
        title=title,
        authors=authors,
        summary=summary,
        categories=categories,
        doi=doi,
        journal_ref=journal_ref,
        submitted_at=_parse_rfc2822_date(published_str),
        updated_at=_parse_rfc2822_date(updated_str),
        all_versions=versions,
    )


async def head_pdf(arxiv_id: str, version: Optional[str] = None) -> ArxivPdfHead:
    url = build_pdf_url(arxiv_id, version)
    async with _http_client() as client:
        resp = await client.head(url)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type")
        content_length = resp.headers.get("Content-Length")
        try:
            cl_int = int(content_length) if content_length is not None else None
        except ValueError:
            cl_int = None
        cd = resp.headers.get("Content-Disposition")
        filename: Optional[str] = None
        if cd and "filename=" in cd:
            filename = cd.split("filename=", 1)[1].strip().strip('"')
        if not filename:
            suffix = (version or "")
            filename = f"{arxiv_id}{suffix}.pdf"
        return ArxivPdfHead(url=url, filename=filename, content_type=content_type, content_length=cl_int)


async def download_pdf(arxiv_id: str, version: Optional[str] = None) -> ArxivPdfResult:
    url = build_pdf_url(arxiv_id, version)
    async with _http_client() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type") or "application/pdf"
        content_length = resp.headers.get("Content-Length")
        try:
            cl_int = int(content_length) if content_length is not None else None
        except ValueError:
            cl_int = None
        cd = resp.headers.get("Content-Disposition")
        filename: Optional[str] = None
        if cd and "filename=" in cd:
            filename = cd.split("filename=", 1)[1].strip().strip('"')
        if not filename:
            suffix = (version or "")
            filename = f"{arxiv_id}{suffix}.pdf"
        pdf_bytes = resp.content
        return ArxivPdfResult(url=str(resp.url), filename=filename, content_type=content_type, content_length=cl_int, pdf_bytes=pdf_bytes)


async def download_pdf_by_url(url: str) -> ArxivPdfResult:
    parsed = await parse_url(url)
    return await download_pdf(parsed.arxiv_id, parsed.version)


async def fetch_pdf_for_processing(id_or_url: str) -> ArxivPdfForProcessing:
    norm = await normalize_id(id_or_url)
    # If version unspecified, prefer latest metadata version
    version = norm.version
    metadata: Optional[ArxivMetadata] = None
    try:
        metadata = await fetch_metadata(norm.arxiv_id)
        if version is None and metadata.latest_version:
            version = metadata.latest_version
    except Exception as e:
        logger.warning("Failed to fetch arXiv metadata for %s: %s", norm.arxiv_id, e)
    pdf = await download_pdf(norm.arxiv_id, version)
    return ArxivPdfForProcessing(pdf_bytes=pdf.pdf_bytes, filename=pdf.filename, metadata=metadata)


# Intentionally no classes; functional, stateless helpers only



# --- Simple search helpers ---

async def search_metadata_by_title(title_query: str) -> Optional[ArxivMetadata]:
    """Search arXiv by exact title phrase and return the first match's metadata, if any.

    This uses the export.arxiv.org ATOM API with a title phrase query.
    """
    if not title_query or not title_query.strip():
        return None
    q = title_query.strip().replace('\n', ' ').strip()
    # Use quoted phrase match; limit to a few results
    search_url = f"{ARXIV_EXPORT_HOST}/api/query?search_query=ti:\"{httpx.QueryParams({'q': q}).get('q')}\"&start=0&max_results=3"
    async with _http_client() as client:
        try:
            resp = await client.get(search_url)
            resp.raise_for_status()
        except Exception:
            logger.exception("arXiv title search failed")
            return None
        content = resp.content
    try:
        root = ET.fromstring(content)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        # Extract id like http://arxiv.org/abs/XXXX
        id_text = (entry.find("atom:id", ns).text or "").strip()
        m = re.search(r"/(?:abs|pdf)/([^/]+)", id_text)
        if not m:
            # Fallback: try title-only parse
            title = _find_text(entry, "atom:title") or ""
            # Without an id, we can still return a partial metadata; but we prefer full
            return ArxivMetadata(
                arxiv_id="",
                latest_version=None,
                title=title,
                authors=[],
                abstract=_find_text(entry, "atom:summary") or "",
                categories=[],
                doi=None,
                journal_ref=None,
                submitted_at=None,
                updated_at=None,
                all_versions=[],
            )
        idver = m.group(1)
        base_id = _split_id_and_version(idver)[0]
        return await fetch_metadata(base_id)
    except Exception:
        logger.exception("Failed to parse arXiv title search response")
        return None

from functools import lru_cache


@lru_cache(maxsize=1)
def _read_arxiv_categories() -> List[str]:
    """Load arXiv categories list from CSV into a flat list of terms."""
    try:
        base_dir = os.path.abspath(os.path.join(os.getcwd(), 'shared', 'arxiv', 'internals'))
        path = os.path.join(base_dir, 'arxiv_categories.csv')
        items: List[str] = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = (line or '').strip()
                if not line or line.lower().startswith('category'):
                    # Skip header or empty
                    continue
                parts = [p.strip() for p in line.split(',')]
                if parts:
                    items.append(parts[0])
        return items
    except Exception:
        logger.exception("Failed to read arXiv categories CSV")
        return []


_to_epoch_seconds = to_epoch_seconds

