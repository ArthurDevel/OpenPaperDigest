"""
ArXiv Paper Discovery DAG

Fetches ALL papers submitted to arXiv for a target date and stores them in the database
with optional Semantic Scholar enrichment (authors, h-index, citations, embeddings).

Target date defaults to 5 days ago to ensure S2 has indexed the papers.
"""

import sys
import time
import httpx
import xmltodict
import pendulum
from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.models import Param
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

sys.path.insert(0, '/opt/airflow')

from sqlalchemy.orm import Session
from shared.db import SessionLocal
from papers.models import ArxivDiscoveredPaper, ArxivPaperAuthor
from papers.db.client_temp import save_arxiv_papers_batch


# ============================================================================
# CONSTANTS
# ============================================================================

DAYS_BACK = 5
ARXIV_API_URL = "https://export.arxiv.org/api/query"
S2_API_URL = "https://api.semanticscholar.org/graph/v1"
TIMEOUT_SECONDS = 60
PAGE_SIZE = 500
S2_BACKOFF_SEQUENCE = [1, 2, 3, 4, 5]
S2_PAPER_BATCH_SIZE = 500   # Max 500 paper IDs per batch request
S2_AUTHOR_BATCH_SIZE = 1000  # Max 1000 author IDs per batch request

DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1",
}


# ============================================================================
# DATABASE HELPERS
# ============================================================================

@contextmanager
def database_session():
    """
    Create a database session with automatic commit/rollback handling.

    Yields:
        Session: SQLAlchemy session for database operations.

    Raises:
        Exception: Any database error that occurs during the transaction.
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================================
# ARXIV API HELPERS
# ============================================================================

def _fetch_arxiv_papers_by_date(
    target_date: datetime,
    max_papers: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Fetch ALL papers from arXiv API for a specific date using pagination.

    Args:
        target_date: Date to fetch papers for.
        max_papers: Maximum number of papers to fetch. None = fetch all.

    Returns:
        List of paper dicts with basic metadata from arXiv.
    """
    date_str = target_date.strftime("%Y%m%d")
    date_start = f"{date_str}0000"
    date_end = f"{date_str}2359"

    search_query = f"submittedDate:[{date_start} TO {date_end}]"

    print(f"Fetching papers from {target_date.strftime('%Y-%m-%d')}...")
    print(f"Query: {search_query}")

    all_papers = []
    start = 0
    total_results = None

    with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        while True:
            params = {
                "search_query": search_query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": start,
                "max_results": PAGE_SIZE,
            }

            resp = client.get(ARXIV_API_URL, params=params)
            resp.raise_for_status()
            raw_xml = resp.text

            data = xmltodict.parse(raw_xml)

            # Get total results on first request
            if total_results is None:
                total_results = int(data["feed"].get("opensearch:totalResults", 0))
                print(f"Total papers available: {total_results}")

            # Extract papers from this page
            entries = data["feed"].get("entry", [])
            if not entries:
                break
            if isinstance(entries, dict):
                entries = [entries]

            for entry in entries:
                paper = _parse_arxiv_entry(entry)
                if paper:
                    all_papers.append(paper)

            print(f"  Fetched {len(all_papers)}/{total_results} papers...")

            # Check if we hit max_papers limit or have all papers
            if max_papers and len(all_papers) >= max_papers:
                all_papers = all_papers[:max_papers]
                break
            if len(all_papers) >= total_results:
                break

            # Next page
            start += PAGE_SIZE
            time.sleep(0.5)  # arXiv API rate limit

    print(f"Fetched {len(all_papers)} papers total")
    return all_papers


def _parse_arxiv_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse a single arXiv API entry into a paper dict.

    Args:
        entry: Raw entry from arXiv API XML response.

    Returns:
        Paper dict with parsed fields, or None if parsing fails.
    """
    id_url = entry.get("id", "")
    arxiv_id = id_url.split("/abs/")[-1] if "/abs/" in id_url else None

    if not arxiv_id:
        return None

    # Extract version and clean ID
    version = None
    if "v" in arxiv_id:
        parts = arxiv_id.rsplit("v", 1)
        arxiv_id = parts[0]
        try:
            version = int(parts[1])
        except ValueError:
            pass

    # Get authors
    authors = entry.get("author", [])
    if isinstance(authors, dict):
        authors = [authors]
    author_names = [a.get("name", "") for a in authors]

    # Get categories
    primary_category = entry.get("arxiv:primary_category", {}).get("@term", "")
    all_categories = entry.get("category", [])
    if isinstance(all_categories, dict):
        all_categories = [all_categories]
    categories = [c.get("@term", "") for c in all_categories if c.get("@term")]

    # Parse published date
    published_at = None
    published_str = entry.get("published")
    if published_str:
        try:
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    return {
        "arxiv_id": arxiv_id,
        "version": version,
        "title": (entry.get("title", "") or "").replace("\n", " ").strip(),
        "abstract": (entry.get("summary", "") or "").strip(),
        "published_at": published_at,
        "primary_category": primary_category,
        "categories": categories,
        "author_names": author_names,
    }


# ============================================================================
# SEMANTIC SCHOLAR BATCH API HELPERS
# ============================================================================

def _post_with_retry(url: str, params: Dict[str, str], json_body: Dict) -> Optional[List]:
    """
    POST to URL with incremental backoff on failure.

    On 429 or error: wait 1s, 2s, 3s, 4s, 5s (then stay at 5s).
    Gives up after 10 consecutive failures.

    Args:
        url: URL to POST to.
        params: Query parameters (e.g., fields).
        json_body: JSON body with IDs.

    Returns:
        List of results, or None if failed.
    """
    backoff_idx = 0
    max_retries = 10

    for attempt in range(max_retries):
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
                resp = client.post(url, params=params, json=json_body)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 429:
                    wait = S2_BACKOFF_SEQUENCE[min(backoff_idx, len(S2_BACKOFF_SEQUENCE) - 1)]
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    backoff_idx += 1
                    continue

                resp.raise_for_status()

        except Exception as e:
            wait = S2_BACKOFF_SEQUENCE[min(backoff_idx, len(S2_BACKOFF_SEQUENCE) - 1)]
            print(f"  Error: {e}, waiting {wait}s...")
            time.sleep(wait)
            backoff_idx += 1

    print(f"  Gave up after {max_retries} attempts")
    return None


def _batch_get_s2_paper_data(arxiv_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch paper data from Semantic Scholar for multiple arXiv IDs.

    Args:
        arxiv_ids: List of arXiv paper IDs (without version).

    Returns:
        Dict mapping arxiv_id -> S2 paper data. Missing papers are not included.
    """
    if not arxiv_ids:
        return {}

    results: Dict[str, Dict[str, Any]] = {}
    url = f"{S2_API_URL}/paper/batch"
    params = {
        "fields": "paperId,authors,authors.authorId,authors.name,citationCount,influentialCitationCount,embedding"
    }

    # Process in batches of S2_PAPER_BATCH_SIZE
    for i in range(0, len(arxiv_ids), S2_PAPER_BATCH_SIZE):
        batch = arxiv_ids[i:i + S2_PAPER_BATCH_SIZE]
        batch_num = i // S2_PAPER_BATCH_SIZE + 1
        total_batches = (len(arxiv_ids) + S2_PAPER_BATCH_SIZE - 1) // S2_PAPER_BATCH_SIZE
        print(f"  Fetching paper batch {batch_num}/{total_batches} ({len(batch)} papers)...")

        # S2 expects ARXIV: prefix for arXiv IDs
        ids_with_prefix = [f"ARXIV:{aid}" for aid in batch]
        json_body = {"ids": ids_with_prefix}

        response = _post_with_retry(url, params, json_body)
        if response:
            # Response is a list in same order as input IDs
            # null entries mean paper not found
            for arxiv_id, paper_data in zip(batch, response):
                if paper_data is not None:
                    results[arxiv_id] = paper_data

        # Small delay between batches to be nice to the API
        if i + S2_PAPER_BATCH_SIZE < len(arxiv_ids):
            time.sleep(0.5)

    print(f"  Found {len(results)}/{len(arxiv_ids)} papers in Semantic Scholar")
    return results


def _batch_get_author_stats(author_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch author stats from Semantic Scholar for multiple author IDs.

    Args:
        author_ids: List of S2 author IDs.

    Returns:
        Dict mapping author_id -> author stats with h-index and computed avgCitationsPerPaper.
    """
    if not author_ids:
        return {}

    results: Dict[str, Dict[str, Any]] = {}
    url = f"{S2_API_URL}/author/batch"
    params = {"fields": "authorId,name,paperCount,citationCount,hIndex"}

    # Process in batches of S2_AUTHOR_BATCH_SIZE
    for i in range(0, len(author_ids), S2_AUTHOR_BATCH_SIZE):
        batch = author_ids[i:i + S2_AUTHOR_BATCH_SIZE]
        batch_num = i // S2_AUTHOR_BATCH_SIZE + 1
        total_batches = (len(author_ids) + S2_AUTHOR_BATCH_SIZE - 1) // S2_AUTHOR_BATCH_SIZE
        print(f"  Fetching author batch {batch_num}/{total_batches} ({len(batch)} authors)...")

        json_body = {"ids": batch}

        response = _post_with_retry(url, params, json_body)
        if response:
            for author_data in response:
                if author_data is not None:
                    author_id = author_data.get("authorId")
                    if author_id:
                        # Compute avgCitationsPerPaper
                        paper_count = author_data.get("paperCount", 0)
                        citation_count = author_data.get("citationCount", 0)
                        author_data["avgCitationsPerPaper"] = (
                            citation_count / paper_count if paper_count > 0 else 0
                        )
                        results[author_id] = author_data

        # Small delay between batches
        if i + S2_AUTHOR_BATCH_SIZE < len(author_ids):
            time.sleep(0.5)

    print(f"  Found stats for {len(results)}/{len(author_ids)} authors")
    return results


def _enrich_papers_batch(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich multiple papers with Semantic Scholar data using batch APIs.

    This is much faster than enriching one paper at a time.

    Args:
        papers: List of paper dicts from arXiv.

    Returns:
        List of enriched paper dicts with S2 data.
    """
    if not papers:
        return []

    # Step 1: Batch fetch all paper data from S2
    arxiv_ids = [p["arxiv_id"] for p in papers]
    print(f"Batch fetching S2 data for {len(arxiv_ids)} papers...")
    s2_paper_data = _batch_get_s2_paper_data(arxiv_ids)

    # Step 2: Collect all unique author IDs from S2 responses
    all_author_ids = set()
    for paper_data in s2_paper_data.values():
        for author in paper_data.get("authors", []):
            author_id = author.get("authorId")
            if author_id:
                all_author_ids.add(author_id)

    # Step 3: Batch fetch all author stats
    print(f"Batch fetching stats for {len(all_author_ids)} unique authors...")
    author_stats = _batch_get_author_stats(list(all_author_ids))

    # Step 4: Combine everything into enriched papers
    enriched_papers = []
    for paper in papers:
        arxiv_id = paper["arxiv_id"]
        s2_data = s2_paper_data.get(arxiv_id)

        # Initialize with null S2 fields
        enriched = {
            **paper,
            "semantic_scholar_id": None,
            "citation_count": None,
            "influential_citation_count": None,
            "embedding_model": None,
            "embedding_vector": None,
            "authors_with_ids": [],
            "avg_author_h_index": None,
            "avg_author_citations_per_paper": None,
            "total_author_h_index": None,
        }

        if not s2_data:
            # S2 doesn't have this paper, use arXiv author names with null S2 IDs
            enriched["authors_with_ids"] = [
                {"name": name, "semantic_scholar_id": None}
                for name in paper.get("author_names", [])
            ]
        else:
            # Basic S2 data
            enriched["semantic_scholar_id"] = s2_data.get("paperId")
            enriched["citation_count"] = s2_data.get("citationCount")
            enriched["influential_citation_count"] = s2_data.get("influentialCitationCount")

            # Embedding
            embedding_data = s2_data.get("embedding")
            if embedding_data:
                enriched["embedding_model"] = embedding_data.get("model")
                enriched["embedding_vector"] = embedding_data.get("vector")

            # Authors with S2 IDs
            s2_authors = s2_data.get("authors", [])
            enriched["authors_with_ids"] = [
                {
                    "name": author.get("name", ""),
                    "semantic_scholar_id": author.get("authorId"),
                }
                for author in s2_authors
            ]

            # Compute author credibility scores using pre-fetched stats
            h_indices = []
            avg_citations = []

            for author in s2_authors:
                author_id = author.get("authorId")
                if not author_id:
                    continue

                stats = author_stats.get(author_id)
                if stats:
                    h_index = stats.get("hIndex")
                    avg_cit = stats.get("avgCitationsPerPaper", 0)

                    if h_index is not None:
                        h_indices.append(h_index)
                    if avg_cit:
                        avg_citations.append(avg_cit)

            if h_indices:
                enriched["avg_author_h_index"] = sum(h_indices) / len(h_indices)
                enriched["total_author_h_index"] = sum(h_indices)
            if avg_citations:
                enriched["avg_author_citations_per_paper"] = sum(avg_citations) / len(avg_citations)

        enriched_papers.append(enriched)

    return enriched_papers


def _convert_to_dto(paper: Dict[str, Any]) -> ArxivDiscoveredPaper:
    """
    Convert enriched paper dict to ArxivDiscoveredPaper DTO.

    Args:
        paper: Enriched paper dict.

    Returns:
        ArxivDiscoveredPaper DTO ready for database insertion.
    """
    authors = [
        ArxivPaperAuthor(
            name=a["name"],
            semantic_scholar_id=a.get("semantic_scholar_id")
        )
        for a in paper.get("authors_with_ids", [])
    ]

    return ArxivDiscoveredPaper(
        arxiv_id=paper["arxiv_id"],
        version=paper.get("version"),
        title=paper["title"],
        abstract=paper.get("abstract"),
        published_at=paper.get("published_at"),
        primary_category=paper.get("primary_category"),
        categories=paper.get("categories", []),
        authors=authors,
        semantic_scholar_id=paper.get("semantic_scholar_id"),
        citation_count=paper.get("citation_count"),
        influential_citation_count=paper.get("influential_citation_count"),
        embedding_model=paper.get("embedding_model"),
        embedding_vector=paper.get("embedding_vector"),
        avg_author_h_index=paper.get("avg_author_h_index"),
        avg_author_citations_per_paper=paper.get("avg_author_citations_per_paper"),
        total_author_h_index=paper.get("total_author_h_index"),
    )


# ============================================================================
# DAG DEFINITION
# ============================================================================

@dag(
    dag_id="arxiv_discovery",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 12 * * *",  # 12 PM UTC daily
    catchup=False,
    tags=["arxiv", "discovery", "papers"],
    params={
        "target_date": Param(
            type=["string", "null"],
            default=None,
            title="Target Date",
            description="Date to fetch papers for (YYYY-MM-DD). Defaults to 5 days ago if not specified."
        ),
        "max_papers": Param(
            type=["integer", "null"],
            default=None,
            title="Max Papers",
            description="Maximum papers to fetch (for debugging). None = fetch all."
        ),
    },
    doc_md="""
    ### ArXiv Paper Discovery DAG

    Fetches ALL papers submitted to arXiv for a target date and stores them in the database
    with optional Semantic Scholar enrichment.

    - **Target date**: Defaults to 5 days ago to ensure S2 has indexed the papers.
    - **Enrichment**: Adds author h-index, citations, and SPECTER embeddings from S2.
    - **Failure handling**: If S2 doesn't have a paper, saves with null S2 fields.
    """,
)
def arxiv_discovery_dag():

    @task
    def fetch_arxiv_papers(target_date: Optional[str], max_papers: Optional[int]) -> List[Dict[str, Any]]:
        """
        Fetch all papers from arXiv for the target date.

        Args:
            target_date: Date string (YYYY-MM-DD) or None for 5 days ago.
            max_papers: Max papers to fetch or None for all.

        Returns:
            List of paper dicts with basic arXiv metadata.
        """
        # Handle Jinja template rendering of None values
        if target_date and target_date not in ("None", "null", ""):
            date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        else:
            date_obj = datetime.now() - timedelta(days=DAYS_BACK)

        # Handle max_papers being a string
        max_papers_int = None
        if max_papers and str(max_papers) not in ("None", "null", ""):
            max_papers_int = int(max_papers)

        print(f"Target date: {date_obj.strftime('%Y-%m-%d')}")
        if max_papers_int:
            print(f"Max papers: {max_papers_int}")

        papers = _fetch_arxiv_papers_by_date(date_obj, max_papers_int)
        print(f"Fetched {len(papers)} papers from arXiv")
        return papers

    @task
    def enrich_papers(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich papers with Semantic Scholar data using batch APIs.

        Uses S2 batch endpoints to fetch paper and author data efficiently:
        - Up to 500 papers per batch request
        - Up to 1000 authors per batch request

        Args:
            papers: List of paper dicts from arXiv.

        Returns:
            List of enriched paper dicts with S2 data.
        """
        if not papers:
            print("No papers to enrich")
            return []

        enriched_papers = _enrich_papers_batch(papers)
        print(f"Enriched {len(enriched_papers)} papers")
        return enriched_papers

    @task
    def save_papers(papers: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Save papers to database.

        Args:
            papers: List of enriched paper dicts.

        Returns:
            Dict with save statistics.
        """
        if not papers:
            print("No papers to save")
            return {"total": 0, "saved": 0}

        dtos = [_convert_to_dto(p) for p in papers]

        with database_session() as db:
            saved_count = save_arxiv_papers_batch(db, dtos)

        print(f"Saved {saved_count}/{len(papers)} papers to database")
        return {"total": len(papers), "saved": saved_count}

    # Task flow
    target_date_param = "{{ params.target_date }}"
    max_papers_param = "{{ params.max_papers }}"

    papers = fetch_arxiv_papers(target_date=target_date_param, max_papers=max_papers_param)
    enriched = enrich_papers(papers)
    save_papers(enriched)


arxiv_discovery_dag()
