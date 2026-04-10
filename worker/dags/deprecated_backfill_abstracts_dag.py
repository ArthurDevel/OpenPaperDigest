"""
Backfill abstracts for existing papers that have an arxiv_id but no abstract.

One-time Airflow DAG that fetches abstracts from the arXiv API for all
papers with an arxiv_id where abstract IS NULL. Processes in batches,
saving each abstract immediately.

Responsibilities:
- Query papers missing abstracts
- Fetch abstracts from arXiv API
- Save each abstract immediately (crash-safe)
- Generate summary report
"""

import sys
import time
import pendulum
from contextlib import contextmanager
from typing import List, Dict, Optional

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord

# ============================================================================
# CONSTANTS
# ============================================================================

FETCH_BATCH_SIZE = 100
ARXIV_API_DELAY = 3.0  # seconds between arXiv API calls (arXiv requires >= 3s)

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


def fetch_papers_without_abstract(batch_size: int = FETCH_BATCH_SIZE) -> List[Dict]:
    """
    Query papers with arxiv_id where abstract IS NULL.

    @param batch_size: Maximum number of papers to fetch per query
    @returns List of dicts with paper_uuid and arxiv_id
    """
    with database_session() as session:
        rows = session.query(
            PaperRecord.paper_uuid,
            PaperRecord.arxiv_id,
        ).filter(
            PaperRecord.arxiv_id.isnot(None),
            PaperRecord.abstract.is_(None),
        ).order_by(PaperRecord.id).limit(batch_size).all()

        return [
            {"paper_uuid": row.paper_uuid, "arxiv_id": row.arxiv_id}
            for row in rows
        ]


def fetch_abstract_from_arxiv(arxiv_id: str) -> Optional[str]:
    """
    Call arXiv API to get the abstract/summary text for a paper.
    Retries on 429 (rate limit) with increasing backoff.

    @param arxiv_id: arXiv paper identifier
    @returns Abstract text, or None if not found
    """
    import asyncio
    import httpx
    from shared.arxiv.client import fetch_metadata

    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            metadata = asyncio.run(fetch_metadata(arxiv_id))
            time.sleep(ARXIV_API_DELAY)
            return metadata.summary if metadata else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < max_retries:
                wait = ARXIV_API_DELAY * (attempt + 2)  # 6s, 9s, 12s
                print(f"  429 rate-limited for {arxiv_id}, waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise


def save_abstract(paper_uuid: str, abstract: str) -> None:
    """
    Update the abstract column for a single paper.

    @param paper_uuid: Paper UUID to update
    @param abstract: Abstract text to save
    """
    with database_session() as session:
        record = session.query(PaperRecord).filter(
            PaperRecord.paper_uuid == paper_uuid
        ).first()
        if record:
            record.abstract = abstract


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id="backfill_abstracts",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time"],
    doc_md="""
    ### Backfill Abstracts DAG

    **ONE-TIME USE DAG**: Fetches abstracts from arXiv API for all papers
    that have an arxiv_id but no abstract stored yet.
    """,
)
def backfill_abstracts_dag():

    @task
    def process_all_papers() -> Dict[str, int]:
        """
        Loop through all papers without abstracts, fetch and save each one.

        @returns Dict with total/updated/failed/skipped counts
        """
        total = 0
        updated = 0
        failed = 0
        skipped = 0

        while True:
            papers = fetch_papers_without_abstract(batch_size=FETCH_BATCH_SIZE)
            if not papers:
                break

            print(f"Fetched batch of {len(papers)} papers (total so far: {total})")

            for paper in papers:
                total += 1
                paper_uuid = paper["paper_uuid"]
                arxiv_id = paper["arxiv_id"]

                if not arxiv_id:
                    skipped += 1
                    continue

                try:
                    abstract = fetch_abstract_from_arxiv(arxiv_id)
                    if abstract:
                        save_abstract(paper_uuid, abstract)
                        updated += 1
                    else:
                        print(f"  SKIP {paper_uuid}: no abstract returned for {arxiv_id}")
                        skipped += 1
                except Exception as e:
                    print(f"  FAIL {paper_uuid} ({arxiv_id}): {e}")
                    failed += 1
                    continue

                if updated % 50 == 0 and updated > 0:
                    print(f"  Progress: {updated} abstracts saved")

        print("\n" + "=" * 50)
        print("BACKFILL ABSTRACTS REPORT")
        print("=" * 50)
        print(f"Total papers:  {total}")
        print(f"Updated:       {updated}")
        print(f"Failed:        {failed}")
        print(f"Skipped:       {skipped}")
        print("=" * 50)

        return {"total": total, "updated": updated, "failed": failed, "skipped": skipped}

    process_all_papers()


backfill_abstracts_dag()
