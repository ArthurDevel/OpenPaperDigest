"""
Daily arXiv ingest DAG -- monitors all cs.* categories for new papers.

Runs daily. For each new paper, fetches arXiv-native metadata and queues the
paper for processing. Semantic Scholar enrichment happens later in the
dedicated enrichment DAG.

Responsibilities:
- Query arXiv API for papers published in the last day across cs.*
- Deduplicate against papers already in the database
- Create paper records with abstract pre-filled
- Persist arXiv classification metadata
"""

import sys
import time
import pendulum
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.client import create_paper
from papers.db.models import PaperRecord

# ============================================================================
# CONSTANTS
# ============================================================================

# arXiv API endpoint and query settings
ARXIV_API_BASE = 'http://export.arxiv.org/api/query'
ARXIV_CATEGORY = 'cs.*'
MAX_RESULTS_PER_QUERY = 200
ARXIV_API_DELAY = 3.0  # seconds between paginated arXiv API calls


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


def build_arxiv_classification_dict(paper: Dict) -> Dict:
    """
    Build the classification JSONB dict from arXiv metadata fields.
    Only includes keys that have non-empty values.

    @param paper: Dict with optional 'categories', 'doi', 'journal_ref' keys
    @returns Dict suitable for the classification JSONB column
    """
    classification = {}
    categories = paper.get('categories')
    if categories:
        classification['arxiv_categories'] = categories
        classification['arxiv_primary_category'] = categories[0]
    if paper.get('doi'):
        classification['arxiv_doi'] = paper['doi']
    if paper.get('journal_ref'):
        classification['arxiv_journal_ref'] = paper['journal_ref']
    return classification


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

            # Extract categories, DOI, and journal_ref from XML entry
            categories = [
                c.attrib.get('term', '')
                for c in entry.findall('atom:category', ns)
                if c.attrib.get('term')
            ]
            doi_elem = entry.find('arxiv:doi', ns)
            doi = (doi_elem.text or '').strip() if doi_elem is not None and doi_elem.text else None
            journal_ref_elem = entry.find('arxiv:journal_ref', ns)
            journal_ref = (journal_ref_elem.text or '').strip() if journal_ref_elem is not None and journal_ref_elem.text else None

            published_elem = entry.find('atom:published', ns)
            published_at = (published_elem.text or '').strip() if published_elem is not None else None

            all_papers.append({
                'arxiv_id': base_id,
                'title': title,
                'authors_str': authors_str,
                'abstract': abstract,
                'categories': categories,
                'doi': doi,
                'journal_ref': journal_ref,
                'published_at': published_at,
            })

        # If we got fewer results than requested, we've reached the end
        if len(entries) < max_results:
            break

        start += max_results
        time.sleep(ARXIV_API_DELAY)

    return all_papers


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id='source_daily_arxiv_ingest',
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
    3. Stores arXiv-native classification metadata
    """,
)
def daily_arxiv_ingest_dag():

    @task
    def ingest_papers() -> Dict[str, int]:
        """
        Fetch new arXiv cs.* papers and ingest them with arXiv metadata only.

        @returns Dict with added/skipped/failed counts
        """
        print('Fetching new arXiv cs.* papers...')
        papers = fetch_new_arxiv_papers()
        print(f'Found {len(papers)} papers from arXiv API')

        added = 0
        skipped = 0
        failed = 0
        with database_session() as session:
            for paper in papers:
                arxiv_id = paper['arxiv_id']
                title = paper['title']

                if not arxiv_id or not title:
                    skipped += 1
                    continue

                try:
                    # Create paper record with abstract
                    # Parse arXiv published date string to datetime
                    pub_at = None
                    if paper.get('published_at'):
                        try:
                            pub_at = datetime.fromisoformat(paper['published_at'].replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            pass

                    paper_dto = create_paper(
                        db=session,
                        arxiv_id=arxiv_id,
                        title=title,
                        authors=paper['authors_str'],
                        abstract=paper['abstract'],
                        published_at=pub_at,
                    )
                    added += 1
                    print(f'  Added {arxiv_id}: {title[:70]}...')

                    # Write arXiv classification metadata to the paper record
                    classification_dict = build_arxiv_classification_dict(paper)
                    if classification_dict:
                        session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_dto.paper_uuid
                        ).update({"classification": classification_dict})

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

        # Report
        print('\n' + '=' * 50)
        print('DAILY ARXIV INGEST REPORT')
        print('=' * 50)
        print(f'Papers from API:     {len(papers)}')
        print(f'Added:               {added}')
        print(f'Skipped (existing):  {skipped}')
        print(f'Failed:              {failed}')
        print('=' * 50)

        return {
            'fetched': len(papers),
            'added': added,
            'skipped': skipped,
            'failed': failed,
        }

    ingest_papers()


daily_arxiv_ingest_dag()
