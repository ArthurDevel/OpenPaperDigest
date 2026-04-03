"""
Client for the Semantic Scholar API.

Uses the free API with optional API key for higher rate limits.
Free tier: 1000 req/s shared globally among all unauthenticated users.
With API key: dedicated 1-10 req/s depending on endpoint.

Responsibilities:
- Fetch paper author data by arXiv ID
- Fetch individual author stats (h-index, citations, etc.)
- Batch fetch paper authors for bulk ingestion
- Batch fetch author stats for bulk ingestion
- Batch fetch comprehensive paper metadata for enrichment
"""

import os
import time
import logging
from typing import List, Optional

import requests

from shared.semantic_scholar.models import (
    S2Author, S2PaperAuthors, S2PaperMetadata, S2PaperReference,
    S2FieldOfStudy, S2PublicationVenue, S2Journal, S2OpenAccessPdf,
)

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

S2_API_BASE = 'https://api.semanticscholar.org/graph/v1'

# The free-tier rate limit is shared globally across ALL unauthenticated users.
# Burst fast and retry with exponential backoff — waiting a fixed delay just
# lets other users consume the pool. Tested in testscripts/7_test_rate_limits.py.
RETRY_BASE_DELAY = 0.1  # seconds, doubles each retry
RETRY_BACKOFF = 2.0
MAX_RETRIES = 5

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


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """
    Make an HTTP request with exponential backoff retry on 429 responses.
    Bursts fast and backs off — optimal for the shared global rate limit pool.

    @param method: HTTP method ('get' or 'post')
    @param url: Request URL
    @param kwargs: Additional arguments passed to requests.get/post
    @returns Response object
    """
    delay = RETRY_BASE_DELAY
    for attempt in range(MAX_RETRIES):
        response = getattr(requests, method)(url, **kwargs)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        logger.warning(f"S2 rate limited (429), retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
        time.sleep(delay)
        delay *= RETRY_BACKOFF

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

    return S2Author(
        s2_author_id=s2_author_id,
        name=data.get('name', 'Unknown'),
        affiliations=data.get('affiliations') or None,
        homepage=data.get('homepage') or None,
        paper_count=data.get('paperCount'),
        citation_count=data.get('citationCount'),
        h_index=data.get('hIndex'),
    )


def fetch_author_stats_batch(s2_author_ids: List[str]) -> List[S2Author]:
    """
    Batch fetch stats for multiple authors. Up to 1000 authors per request.

    @param s2_author_ids: List of Semantic Scholar author IDs
    @returns List of S2Author with stats (h_index, citation_count, etc.)
    """
    url = f'{S2_API_BASE}/author/batch'
    params = {'fields': 'name,affiliations,homepage,paperCount,citationCount,hIndex'}

    response = _request_with_retry(
        'post', url,
        headers=_get_headers(),
        params=params,
        json={'ids': s2_author_ids},
        timeout=60,
    )
    results = response.json()

    authors = []
    for i, author_data in enumerate(results):
        if author_data is None:
            continue

        authors.append(S2Author(
            s2_author_id=s2_author_ids[i],
            name=author_data.get('name', 'Unknown'),
            affiliations=author_data.get('affiliations') or None,
            homepage=author_data.get('homepage') or None,
            paper_count=author_data.get('paperCount'),
            citation_count=author_data.get('citationCount'),
            h_index=author_data.get('hIndex'),
        ))

    return authors


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


# All S2 fields requested for paper metadata enrichment
S2_METADATA_FIELDS = (
    'paperId,corpusId,externalIds,'
    'citationCount,referenceCount,influentialCitationCount,'
    's2FieldsOfStudy,publicationTypes,'
    'venue,publicationVenue,journal,'
    'year,publicationDate,'
    'tldr,isOpenAccess,openAccessPdf,'
    'embedding.specter_v2'
)


def fetch_paper_metadata_batch(arxiv_ids: List[str]) -> List[S2PaperMetadata]:
    """
    Batch fetch comprehensive paper metadata from S2. Up to 500 papers per request.
    Skips null entries (papers S2 cannot find). Populates arxiv_id from externalIds.ArXiv
    for correlation back to input papers.

    @param arxiv_ids: List of arXiv identifiers (e.g. ["2301.00001", "2301.00002"])
    @returns List of S2PaperMetadata DTOs for papers S2 found
    """
    url = f'{S2_API_BASE}/paper/batch'
    params = {'fields': S2_METADATA_FIELDS}
    paper_ids = [f'ARXIV:{aid}' for aid in arxiv_ids]

    response = _request_with_retry(
        'post', url,
        headers=_get_headers(),
        params=params,
        json={'ids': paper_ids},
        timeout=60,
    )
    results = response.json()

    metadata_list = []
    for i, data in enumerate(results):
        if data is None:
            continue

        external_ids = data.get('externalIds', {}) or {}

        # Parse nested fields of study
        s2_fields = None
        raw_fields = data.get('s2FieldsOfStudy')
        if raw_fields:
            s2_fields = [
                S2FieldOfStudy(category=f['category'], source=f['source'])
                for f in raw_fields
            ]

        # Parse publication venue
        pub_venue = None
        raw_venue = data.get('publicationVenue')
        if raw_venue:
            pub_venue = S2PublicationVenue(
                id=raw_venue.get('id'),
                name=raw_venue.get('name'),
                type=raw_venue.get('type'),
                alternate_names=raw_venue.get('alternate_names') or raw_venue.get('alternateNames'),
                url=raw_venue.get('url'),
            )

        # Parse journal
        journal = None
        raw_journal = data.get('journal')
        if raw_journal:
            journal = S2Journal(
                name=raw_journal.get('name'),
                volume=raw_journal.get('volume'),
                pages=raw_journal.get('pages'),
            )

        # Parse open access PDF
        oa_pdf = None
        raw_oa = data.get('openAccessPdf')
        if raw_oa:
            oa_pdf = S2OpenAccessPdf(
                url=raw_oa.get('url') or None,
                status=raw_oa.get('status') or None,
            )

        # Extract tldr text from the tldr object
        tldr_text = None
        raw_tldr = data.get('tldr')
        if raw_tldr and raw_tldr.get('text'):
            tldr_text = raw_tldr['text']

        # Extract SPECTER v2 embedding
        embedding = None
        raw_embedding = data.get('embedding')
        if raw_embedding and raw_embedding.get('vector'):
            embedding = raw_embedding['vector']

        metadata_list.append(S2PaperMetadata(
            paper_id=data.get('paperId', ''),
            arxiv_id=external_ids.get('ArXiv') or (arxiv_ids[i] if i < len(arxiv_ids) else None),
            corpus_id=data.get('corpusId'),
            external_ids=external_ids or None,
            citation_count=data.get('citationCount'),
            reference_count=data.get('referenceCount'),
            influential_citation_count=data.get('influentialCitationCount'),
            s2_fields_of_study=s2_fields,
            publication_types=data.get('publicationTypes'),
            venue=data.get('venue') or None,
            publication_venue=pub_venue,
            journal=journal,
            year=data.get('year'),
            publication_date=data.get('publicationDate'),
            tldr=tldr_text,
            is_open_access=data.get('isOpenAccess'),
            open_access_pdf=oa_pdf,
            embedding=embedding,
        ))

    return metadata_list


def fetch_paper_references_batch(s2_paper_ids: List[str]) -> List[S2PaperReference]:
    """
    Batch fetch references for multiple papers. Up to 500 raw S2 paper IDs per request.
    Skips null entries (papers S2 cannot find) and null reference targets within entries.
    Uses input index to correlate source_s2_id back to input order.

    @param s2_paper_ids: List of raw S2 paper IDs (NOT ARXIV: prefixed)
    @returns List of S2PaperReference edges
    """
    url = f'{S2_API_BASE}/paper/batch'
    # Note: references.isInfluential is not supported by the batch endpoint
    # (only BasePaper subfields like paperId are valid). isInfluential is only
    # available via the single-paper GET /paper/{id}/references endpoint.
    params = {'fields': 'references.paperId'}

    response = _request_with_retry(
        'post', url,
        headers=_get_headers(),
        params=params,
        json={'ids': s2_paper_ids},
        timeout=120,
    )
    results = response.json()

    references = []
    for i, paper_data in enumerate(results):
        if paper_data is None:
            continue

        source_id = s2_paper_ids[i]
        for ref in (paper_data.get('references') or []):
            if ref is None:
                continue
            cited_id = ref.get('paperId')
            if cited_id is None:
                continue
            references.append(S2PaperReference(
                source_s2_id=source_id,
                cited_s2_id=cited_id,
                is_influential=ref.get('isInfluential'),
            ))

    return references
