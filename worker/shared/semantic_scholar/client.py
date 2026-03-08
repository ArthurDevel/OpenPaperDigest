"""
Client for the Semantic Scholar API.

Uses the free API with optional API key for higher rate limits.
Free tier: 100 requests/5 minutes. With API key: 1 request/second.

Responsibilities:
- Fetch paper author data by arXiv ID
- Fetch individual author stats (h-index, citations, etc.)
- Batch fetch paper authors for bulk ingestion
"""

import os
import time
import logging
from typing import List, Optional

import requests

from shared.semantic_scholar.models import S2Author, S2PaperAuthors

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

S2_API_BASE = 'https://api.semanticscholar.org/graph/v1'
RATE_LIMIT_DELAY = 4.0  # seconds between requests (free tier: 100 req / 5 min, need >= 3s)
MAX_RETRIES = 3
RETRY_BASE_DELAY = 10.0  # seconds, doubles each retry on 429

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _get_headers() -> dict:
    """Build request headers, including API key if available."""
    headers = {'Accept': 'application/json'}
    api_key = os.environ.get('SEMANTIC_SCHOLAR_API_KEY')
    if api_key:
        headers['x-api-key'] = api_key
    return headers


def _rate_limit() -> None:
    """Sleep to respect Semantic Scholar rate limits."""
    time.sleep(RATE_LIMIT_DELAY)


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """
    Make an HTTP request with retry on 429 (rate limit) responses.
    Uses exponential backoff starting at RETRY_BASE_DELAY seconds.

    @param method: HTTP method ('get' or 'post')
    @param url: Request URL
    @param kwargs: Additional arguments passed to requests.get/post
    @returns Response object
    """
    for attempt in range(MAX_RETRIES):
        response = getattr(requests, method)(url, **kwargs)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        delay = RETRY_BASE_DELAY * (2 ** attempt)
        logger.warning(f"S2 rate limited (429), retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
        time.sleep(delay)

    # Final attempt, let it raise
    response = getattr(requests, method)(url, **kwargs)
    response.raise_for_status()
    return response


# ============================================================================
# MAIN ENTRYPOINTS
# ============================================================================


def fetch_paper_authors(arxiv_id: str) -> S2PaperAuthors:
    """
    Fetch authors for a paper by its arXiv ID.

    @param arxiv_id: arXiv identifier (e.g. "2301.00001")
    @returns S2PaperAuthors with list of authors and their S2 IDs
    """
    url = f'{S2_API_BASE}/paper/ARXIV:{arxiv_id}'
    params = {'fields': 'authors,authors.authorId,authors.name'}

    response = _request_with_retry('get', url, headers=_get_headers(), params=params, timeout=30)
    data = response.json()

    authors = []
    for author_data in data.get('authors', []):
        author_id = author_data.get('authorId')
        if not author_id:
            continue
        authors.append(S2Author(
            s2_author_id=author_id,
            name=author_data.get('name', 'Unknown'),
        ))

    _rate_limit()

    return S2PaperAuthors(
        s2_paper_id=data.get('paperId', ''),
        arxiv_id=arxiv_id,
        authors=authors,
    )


def fetch_author_stats(s2_author_id: str) -> S2Author:
    """
    Fetch full stats for an author by their Semantic Scholar ID.

    @param s2_author_id: Semantic Scholar author ID
    @returns S2Author with paper_count, citation_count, h_index, etc.
    """
    url = f'{S2_API_BASE}/author/{s2_author_id}'
    params = {'fields': 'name,affiliations,homepage,paperCount,citationCount,hIndex'}

    response = _request_with_retry('get', url, headers=_get_headers(), params=params, timeout=30)
    data = response.json()

    _rate_limit()

    return S2Author(
        s2_author_id=s2_author_id,
        name=data.get('name', 'Unknown'),
        affiliations=data.get('affiliations') or None,
        homepage=data.get('homepage') or None,
        paper_count=data.get('paperCount'),
        citation_count=data.get('citationCount'),
        h_index=data.get('hIndex'),
    )


def fetch_paper_authors_batch(arxiv_ids: List[str]) -> List[S2PaperAuthors]:
    """
    Batch fetch authors for multiple papers. Up to 500 papers per request.

    @param arxiv_ids: List of arXiv identifiers
    @returns List of S2PaperAuthors, one per paper
    """
    url = f'{S2_API_BASE}/paper/batch'
    params = {'fields': 'externalIds,authors,authors.authorId,authors.name'}

    paper_ids = [f'ARXIV:{aid}' for aid in arxiv_ids]

    response = _request_with_retry(
        'post', url,
        headers=_get_headers(),
        params=params,
        json={'ids': paper_ids},
        timeout=60,
    )
    results = response.json()

    _rate_limit()

    paper_authors_list = []
    for i, paper_data in enumerate(results):
        if paper_data is None:
            continue

        authors = []
        for author_data in paper_data.get('authors', []):
            author_id = author_data.get('authorId')
            if not author_id:
                continue
            authors.append(S2Author(
                s2_author_id=author_id,
                name=author_data.get('name', 'Unknown'),
            ))

        external_ids = paper_data.get('externalIds', {})
        arxiv_id = external_ids.get('ArXiv') or (arxiv_ids[i] if i < len(arxiv_ids) else None)

        paper_authors_list.append(S2PaperAuthors(
            s2_paper_id=paper_data.get('paperId', ''),
            arxiv_id=arxiv_id,
            authors=authors,
        ))

    return paper_authors_list
