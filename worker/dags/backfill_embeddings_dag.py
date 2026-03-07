"""
Backfill embeddings for all existing papers that have no embedding yet.

One-time Airflow DAG that generates 1536-dim embeddings via OpenRouter for all
completed papers where embedding IS NULL. Uses the summaries column to get the
five_minute_summary text; falls back to title-only if summaries is NULL.

Processes ALL papers in batches of 100 (fetched from DB), saving each embedding
immediately after generation so progress is never lost on crash.

Responsibilities:
- Loop through all completed papers without embeddings
- Generate embeddings one at a time via OpenRouter
- Save each embedding immediately after generation (crash-safe)
- Generate summary report
"""

import sys
import pendulum
from contextlib import contextmanager
from typing import List, Dict

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord

# ============================================================================
# CONSTANTS
# ============================================================================

# Number of papers to fetch per DB query (not a processing limit)
FETCH_BATCH_SIZE = 100

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


def fetch_papers_without_embeddings(batch_size: int = FETCH_BATCH_SIZE) -> List[Dict]:
    """
    Query a batch of papers where status='completed' AND embedding IS NULL.

    Args:
        batch_size: Maximum number of papers to fetch per query.

    Returns:
        List[Dict]: List of dicts with paper_uuid, title, and summaries.
    """
    with database_session() as session:
        rows = session.query(
            PaperRecord.paper_uuid,
            PaperRecord.title,
            PaperRecord.summaries,
            PaperRecord.abstract,
        ).filter(
            PaperRecord.status.in_(['completed', 'partially_completed']),
            PaperRecord.embedding.is_(None),
        ).order_by(PaperRecord.id).limit(batch_size).all()

        return [
            {
                "paper_uuid": row.paper_uuid,
                "title": row.title,
                "summaries": row.summaries,
                "abstract": row.abstract,
            }
            for row in rows
        ]


def save_embedding(paper_uuid: str, embedding: List[float]) -> None:
    """
    Save a single embedding to the database immediately.
    Each call opens and commits its own transaction so progress is never lost.

    Args:
        paper_uuid: The paper to update.
        embedding: The 1536-dim embedding vector.
    """
    with database_session() as session:
        record = session.query(PaperRecord).filter(
            PaperRecord.paper_uuid == paper_uuid
        ).first()
        if record:
            record.embedding = embedding


# ============================================================================
# DAG DEFINITION
# ============================================================================

@dag(
    dag_id="backfill_embeddings",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time"],
    doc_md="""
    ### Backfill Embeddings DAG

    **ONE-TIME USE DAG**: Generates 1536-dim embeddings via OpenRouter for ALL
    completed papers that have no embedding yet.

    Processes all papers by fetching batches of 100 from the DB and looping
    until none remain. Each embedding is saved immediately after generation
    (crash-safe). Per-paper error handling logs failures and continues.
    """,
)
def backfill_embeddings_dag():

    @task
    def process_all_papers() -> Dict[str, int]:
        """
        Loop through all papers without embeddings, generate and save each one.
        Fetches in batches of 100 from DB, saves each embedding immediately.

        Returns:
            Dict with updated/failed/skipped counts.
        """
        from paperprocessor.embedding import generate_embedding

        total = 0
        updated = 0
        failed = 0
        skipped = 0

        while True:
            papers = fetch_papers_without_embeddings(batch_size=FETCH_BATCH_SIZE)
            if not papers:
                break

            print(f"Fetched batch of {len(papers)} papers (total so far: {total})")

            for paper in papers:
                total += 1
                paper_uuid = paper["paper_uuid"]
                title = paper["title"]

                if not title:
                    print(f"  SKIP {paper_uuid}: no title")
                    skipped += 1
                    continue

                try:
                    abstract = paper.get("abstract")

                    embedding = generate_embedding(title, abstract)
                    save_embedding(paper_uuid, embedding)
                    updated += 1

                    if updated % 50 == 0:
                        print(f"  Progress: {updated} papers embedded")

                except Exception as e:
                    print(f"  FAIL {paper_uuid}: {e}")
                    failed += 1
                    continue

        # Final report
        print("\n" + "=" * 50)
        print("BACKFILL EMBEDDINGS REPORT")
        print("=" * 50)
        print(f"Total papers:  {total}")
        print(f"Updated:       {updated}")
        print(f"Failed:        {failed}")
        print(f"Skipped:       {skipped}")
        print("=" * 50)

        return {"total": total, "updated": updated, "failed": failed, "skipped": skipped}

    process_all_papers()


backfill_embeddings_dag()
