"""
Supabase Storage client wrapper for paper assets.

Handles uploading, downloading, and deleting paper files in a private Supabase Storage bucket.

Responsibilities:
- Upload paper assets after processing (thumbnail, metadata with pipeline_version)
- Download paper content (handles both v1 OCR format and v2 PDF-direct format)
- Generate signed URLs for thumbnails and figures (private bucket)
- Delete all assets for a paper (handles both old and new format)
- Lazy-initialize the Supabase client from config
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from supabase import create_client, Client

from shared.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

BUCKET_NAME = "papers"
SIGNED_URL_EXPIRY_SECONDS = 3600


# ============================================================================
# TYPES
# ============================================================================

@dataclass
class StoredPaperContent:
    """Content downloaded from storage for a single paper."""

    final_markdown: str
    sections: List[Dict]
    figures: List[Dict]
    metadata: dict


# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================

_client: Optional[Client] = None


def _get_client() -> Client:
    """Return the lazily-initialized Supabase client.

    Returns:
        Supabase client instance configured with service key.

    Raises:
        RuntimeError: If SUPABASE_URL or SUPABASE_SERVICE_KEY are not set.
    """
    global _client
    if _client is None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment"
            )
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def _bucket():
    """Return the storage bucket handle.

    Returns:
        Supabase storage bucket reference for the papers bucket.
    """
    return _get_client().storage.from_(BUCKET_NAME)


# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

def upload_paper_assets(
    paper_uuid: str,
    thumbnail_bytes: bytes,
    metadata: dict,
) -> None:
    """Upload processed paper assets to Supabase Storage.

    Uploads thumbnail.png and metadata.json (with pipeline_version: 2) under {paper_uuid}/.

    Args:
        paper_uuid: Unique identifier for the paper.
        thumbnail_bytes: Raw PNG bytes for the thumbnail (NOT base64).
        metadata: Dict of usage summary, processing stats, cost info.
    """
    bucket = _bucket()
    prefix = paper_uuid

    # Add pipeline version to metadata
    metadata["pipeline_version"] = 2

    # Upload thumbnail
    bucket.upload(
        f"{prefix}/thumbnail.png",
        thumbnail_bytes,
        {"content-type": "image/png", "upsert": "true"},
    )

    # Upload metadata JSON
    bucket.upload(
        f"{prefix}/metadata.json",
        json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
        {"content-type": "application/json", "upsert": "true"},
    )


def download_paper_content(paper_uuid: str) -> StoredPaperContent:
    """Download content for a paper from storage.

    Checks pipeline_version from metadata.json first:
    - v2 papers: return empty final_markdown, empty sections/figures (they don't exist in storage)
    - v1 papers (or no version): download content.md, sections.json, figures.json as before

    Args:
        paper_uuid: Unique identifier for the paper.

    Returns:
        StoredPaperContent with all text content fields populated.
    """
    bucket = _bucket()
    prefix = paper_uuid

    # Always download metadata first to check pipeline version
    metadata_bytes = bucket.download(f"{prefix}/metadata.json")
    metadata = json.loads(metadata_bytes.decode("utf-8"))

    pipeline_version = metadata.get("pipeline_version", 1)

    # v2 papers: no content.md, sections.json, or figures.json in storage
    if pipeline_version >= 2:
        return StoredPaperContent(
            final_markdown="",
            sections=[],
            figures=[],
            metadata=metadata,
        )

    # v1 papers: download all legacy files
    markdown_bytes = bucket.download(f"{prefix}/content.md")
    sections_bytes = bucket.download(f"{prefix}/sections.json")
    figures_bytes = bucket.download(f"{prefix}/figures.json")

    return StoredPaperContent(
        final_markdown=markdown_bytes.decode("utf-8"),
        sections=json.loads(sections_bytes.decode("utf-8")),
        figures=json.loads(figures_bytes.decode("utf-8")),
        metadata=metadata,
    )


def download_markdown(paper_uuid: str) -> str:
    """Download only the markdown content for a paper.

    Checks metadata for pipeline_version first. Returns empty string for v2 papers.

    Args:
        paper_uuid: Unique identifier for the paper.

    Returns:
        The raw markdown string from content.md, or empty string for v2 papers.
    """
    bucket = _bucket()
    prefix = paper_uuid

    # Check pipeline version from metadata
    try:
        metadata_bytes = bucket.download(f"{prefix}/metadata.json")
        metadata = json.loads(metadata_bytes.decode("utf-8"))
        if metadata.get("pipeline_version", 1) >= 2:
            return ""
    except Exception:
        # If metadata doesn't exist, try legacy download
        pass

    markdown_bytes = bucket.download(f"{paper_uuid}/content.md")
    return markdown_bytes.decode("utf-8")


def get_thumbnail_url(paper_uuid: str) -> str:
    """Generate a signed URL for a paper's thumbnail.

    Args:
        paper_uuid: Unique identifier for the paper.

    Returns:
        Signed HTTPS URL for thumbnail.png (valid for 1 hour).

    Raises:
        RuntimeError: If signed URL generation fails.
    """
    path = f"{paper_uuid}/thumbnail.png"
    response = _bucket().create_signed_url(path, SIGNED_URL_EXPIRY_SECONDS)
    signed_url = response.get("signedURL")
    if not signed_url:
        raise RuntimeError(
            f"Failed to generate signed URL for {path}: {response}"
        )
    return signed_url


def get_figure_url(paper_uuid: str, figure_id: str) -> str:
    """Generate a signed URL for a specific figure image.

    Args:
        paper_uuid: Unique identifier for the paper.
        figure_id: The figure identifier (used as filename without extension).

    Returns:
        Signed HTTPS URL for the figure PNG (valid for 1 hour).

    Raises:
        RuntimeError: If signed URL generation fails.
    """
    path = f"{paper_uuid}/figures/{figure_id}.png"
    response = _bucket().create_signed_url(path, SIGNED_URL_EXPIRY_SECONDS)
    signed_url = response.get("signedURL")
    if not signed_url:
        raise RuntimeError(
            f"Failed to generate signed URL for {path}: {response}"
        )
    return signed_url


def delete_paper_assets(paper_uuid: str) -> None:
    """Delete all storage files for a paper.

    Handles both v1 (OCR format with content.md, figures, sections) and
    v2 (just thumbnail + metadata). Includes all possible paths regardless
    of format -- the remove call handles non-existent files gracefully.

    Args:
        paper_uuid: Unique identifier for the paper.
    """
    bucket = _bucket()
    prefix = paper_uuid

    # Always include both old and new format paths
    paths_to_delete = [
        f"{prefix}/thumbnail.png",
        f"{prefix}/metadata.json",
        f"{prefix}/content.md",
        f"{prefix}/sections.json",
        f"{prefix}/figures.json",
    ]

    # Try to read figures.json to find individual figure files (v1 papers only)
    try:
        figures_bytes = bucket.download(f"{prefix}/figures.json")
        figures_list = json.loads(figures_bytes.decode("utf-8"))
        for fig in figures_list:
            identifier = fig.get("identifier")
            if identifier:
                paths_to_delete.append(f"{prefix}/figures/{identifier}.png")
    except Exception:
        # figures.json doesn't exist (v2 paper) or is malformed -- skip figure deletion
        pass

    bucket.remove(paths_to_delete)
