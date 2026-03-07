"""
Daily arXiv ingest DAG -- monitors all cs.* categories for new papers.

Runs daily. For each new paper, fetches metadata (title, authors, abstract)
from the arXiv API and author IDs from Semantic Scholar, then queues the paper
for processing with all data attached upfront.

Responsibilities:
- Query arXiv API for papers published in the last day across cs.*
- Deduplicate against papers already in the database
- Create paper records with abstract pre-filled
- Link authors via Semantic Scholar (best-effort, non-blocking)
"""

import sys
import asyncio
import time
import pendulum
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict, Optional

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.client import create_paper
from papers.db.models import PaperRecord, AuthorRecord, PaperAuthorRecord

# ============================================================================
# CONSTANTS
# ============================================================================

# arXiv API endpoint and query settings
ARXIV_API_BASE = 'http://export.arxiv.org/api/query'
ARXIV_CATEGORY = 'cs.*'
MAX_RESULTS_PER_QUERY = 200
ARXIV_API_DELAY = 3.0  # seconds between paginated arXiv API calls
S2_LINK_DELAY = 1.0    # seconds between Semantic Scholar calls


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


@contextmanager
def database_session():
    """
    Create a database session with automatic commit/rollback handling.

    Yields:
        Session: SQLAlchemy session for database operations
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


def fetch_new_arxiv_papers(max_results: int = MAX_RESULTS_PER_QUERY) -> List[Dict]:
    """
    Query arXiv API for recent cs.* papers, sorted by submission date.

    Uses submittedDate range to only get papers from the last 2 days,
    with a buffer to handle timezone differences and delayed indexing.

    @param max_results: Maximum number of papers to fetch per page
    @returns List of dicts with arxiv_id, title, authors_str, abstract
    """
    from shared.arxiv.models import ArxivMetadata
    import xml.etree.ElementTree as ET
    import httpx

    # Query for papers submitted in the last 2 days (buffer for indexing delays)
    now = pendulum.now('UTC')
    two_days_ago = now.subtract(days=2)
    date_from = two_days_ago.format('YYYYMMDD') + '0000'
    date_to = now.format('YYYYMMDD') + '2359'

    all_papers = []
    start = 0

    while True:
        query_url = (
            f"{ARXIV_API_BASE}?search_query=cat:{ARXIV_CATEGORY}"
            f"+AND+submittedDate:[{date_from}+TO+{date_to}]"
            f"&start={start}&max_results={max_results}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )

        response = httpx.get(query_url, timeout=60, follow_redirects=True)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom',
        }

        entries = root.findall('atom:entry', ns)
        if not entries:
            break

        for entry in entries:
            # Extract arXiv ID from the entry id URL
            id_text = (entry.find('atom:id', ns).text or '').strip()
            # ID looks like http://arxiv.org/abs/2503.12345v1
            import re
            m = re.search(r'/abs/([^/]+)', id_text)
            if not m:
                continue

            id_with_version = m.group(1)
            # Strip version suffix to get base arxiv_id
            base_id = re.sub(r'v\d+$', '', id_with_version)

            title_elem = entry.find('atom:title', ns)
            title = (title_elem.text or '').strip().replace('\n', ' ') if title_elem is not None else None

            summary_elem = entry.find('atom:summary', ns)
            abstract = (summary_elem.text or '').strip() if summary_elem is not None else None

            # Build authors string
            author_names = []
            for a in entry.findall('atom:author', ns):
                name_elem = a.find('atom:name', ns)
                if name_elem is not None and name_elem.text:
                    author_names.append(name_elem.text.strip())
            authors_str = ', '.join(author_names) if author_names else None

            all_papers.append({
                'arxiv_id': base_id,
                'title': title,
                'authors_str': authors_str,
                'abstract': abstract,
            })

        # If we got fewer results than requested, we've reached the end
        if len(entries) < max_results:
            break

        start += max_results
        time.sleep(ARXIV_API_DELAY)

    return all_papers


def link_authors_for_paper(paper_db_id: int, arxiv_id: str) -> int:
    """
    Fetch author IDs from Semantic Scholar and link them to the paper.
    Best-effort: failures are logged but don't block ingestion.

    @param paper_db_id: Database primary key of the paper
    @param arxiv_id: arXiv identifier for S2 lookup
    @returns Number of authors linked
    """
    from shared.semantic_scholar.client import fetch_paper_authors

    try:
        s2_result = fetch_paper_authors(arxiv_id)
    except Exception as e:
        print(f"    S2 lookup failed for {arxiv_id}: {e}")
        return 0

    linked = 0

    with database_session() as session:
        for order, s2_author in enumerate(s2_result.authors, start=1):
            # Upsert author record
            existing = session.query(AuthorRecord).filter(
                AuthorRecord.s2_author_id == s2_author.s2_author_id
            ).first()

            if existing:
                author_id = existing.id
            else:
                new_author = AuthorRecord(
                    s2_author_id=s2_author.s2_author_id,
                    name=s2_author.name,
                )
                session.add(new_author)
                session.flush()
                author_id = new_author.id

            # Create junction row (skip duplicates)
            existing_link = session.query(PaperAuthorRecord).filter(
                PaperAuthorRecord.paper_id == paper_db_id,
                PaperAuthorRecord.author_id == author_id,
            ).first()

            if not existing_link:
                session.add(PaperAuthorRecord(
                    paper_id=paper_db_id,
                    author_id=author_id,
                    author_order=order,
                ))
                linked += 1

    return linked


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id='daily_arxiv_ingest',
    start_date=pendulum.datetime(2026, 3, 6, tz='UTC'),
    schedule='0 8 * * *',  # Daily at 08:00 UTC (after arXiv daily update)
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'ingestion', 'arxiv', 'daily'],
    doc_md="""
    ### Daily arXiv Ingest DAG

    Monitors all `cs.*` arXiv categories for new papers published in the last
    2 days. For each new paper:
    1. Fetches metadata (title, authors, abstract) from arXiv API
    2. Creates a paper record queued for processing
    3. Links author IDs from Semantic Scholar (best-effort)
    """,
)
def daily_arxiv_ingest_dag():

    @task
    def ingest_papers() -> Dict[str, int]:
        """
        Fetch new arXiv cs.* papers and ingest them with metadata + author links.

        @returns Dict with added/skipped/failed counts
        """
        print('Fetching new arXiv cs.* papers...')
        papers = fetch_new_arxiv_papers()
        print(f'Found {len(papers)} papers from arXiv API')

        added = 0
        skipped = 0
        failed = 0
        authors_linked_total = 0

        with database_session() as session:
            for paper in papers:
                arxiv_id = paper['arxiv_id']
                title = paper['title']

                if not arxiv_id or not title:
                    skipped += 1
                    continue

                try:
                    # Create paper record with abstract
                    paper_dto = create_paper(
                        db=session,
                        arxiv_id=arxiv_id,
                        title=title,
                        authors=paper['authors_str'],
                        abstract=paper['abstract'],
                    )
                    added += 1
                    print(f'  Added {arxiv_id}: {title[:70]}...')

                except ValueError as e:
                    if 'already exists' in str(e):
                        skipped += 1
                    else:
                        print(f'  FAIL {arxiv_id}: {e}')
                        failed += 1
                    continue
                except Exception as e:
                    print(f'  FAIL {arxiv_id}: {e}')
                    failed += 1
                    continue

        # Link authors in a separate pass (best-effort, outside the main transaction)
        print('\nLinking authors via Semantic Scholar...')
        for paper in papers:
            arxiv_id = paper['arxiv_id']
            if not arxiv_id:
                continue

            # Look up the DB record to get the primary key
            try:
                with database_session() as session:
                    record = session.query(PaperRecord).filter(
                        PaperRecord.arxiv_id == arxiv_id
                    ).first()
                    if not record:
                        continue
                    paper_db_id = record.id

                linked = link_authors_for_paper(paper_db_id, arxiv_id)
                authors_linked_total += linked
            except Exception as e:
                print(f'  Author link failed for {arxiv_id}: {e}')

        # Report
        print('\n' + '=' * 50)
        print('DAILY ARXIV INGEST REPORT')
        print('=' * 50)
        print(f'Papers from API:     {len(papers)}')
        print(f'Added:               {added}')
        print(f'Skipped (existing):  {skipped}')
        print(f'Failed:              {failed}')
        print(f'Authors linked:      {authors_linked_total}')
        print('=' * 50)

        return {
            'fetched': len(papers),
            'added': added,
            'skipped': skipped,
            'failed': failed,
            'authors_linked': authors_linked_total,
        }

    ingest_papers()


daily_arxiv_ingest_dag()
