"""
Backfill author data from Semantic Scholar for all existing papers.

One-time Airflow DAG that populates the `authors` and `paper_authors` tables.
Uses the S2 batch endpoint (/paper/batch, up to 500 papers per request) to
minimize API calls and avoid rate limits.

Responsibilities:
- Find papers without author links in paper_authors
- Batch-fetch author IDs from Semantic Scholar API (1 request per batch)
- Upsert author records
- Create paper_authors junction rows
- Refresh author stats (h-index, citation count, paper count)
"""

import sys
import pendulum
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Dict

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord, AuthorRecord, PaperAuthorRecord

# ============================================================================
# CONSTANTS
# ============================================================================

# S2 batch endpoint accepts up to 500 IDs per request
BATCH_SIZE = 500
STALE_DAYS = 7  # refresh author stats older than this

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


def fetch_papers_without_author_links(batch_size: int = BATCH_SIZE) -> List[Dict]:
    """
    Query papers with arxiv_id that have no entries in paper_authors.

    @param batch_size: Maximum number of papers to fetch
    @returns List of dicts with paper id, paper_uuid, and arxiv_id
    """
    with database_session() as session:
        rows = session.query(
            PaperRecord.id,
            PaperRecord.paper_uuid,
            PaperRecord.arxiv_id,
        ).filter(
            PaperRecord.arxiv_id.isnot(None),
            ~PaperRecord.id.in_(
                session.query(PaperAuthorRecord.paper_id).distinct()
            ),
        ).order_by(PaperRecord.id).limit(batch_size).all()

        return [
            {"id": row.id, "paper_uuid": row.paper_uuid, "arxiv_id": row.arxiv_id}
            for row in rows
        ]


def link_batch_authors(papers: List[Dict]) -> Dict[str, int]:
    """
    Batch-fetch author IDs from Semantic Scholar and create DB records.
    Uses /paper/batch endpoint (1 API call for up to 500 papers).

    @param papers: List of dicts with id, paper_uuid, arxiv_id
    @returns Dict with counts of authors_linked, authors_created, papers_failed
    """
    from shared.semantic_scholar.client import fetch_paper_authors_batch

    arxiv_ids = [p["arxiv_id"] for p in papers]
    arxiv_to_paper = {p["arxiv_id"]: p for p in papers}

    # Single batch API call
    print(f"  Sending {len(arxiv_ids)} IDs to S2 batch: {arxiv_ids[:5]}{'...' if len(arxiv_ids) > 5 else ''}")
    try:
        batch_results = fetch_paper_authors_batch(arxiv_ids)
    except Exception as e:
        print(f"  S2 batch call failed: {e}")
        return {"authors_linked": 0, "authors_created": 0, "papers_failed": len(papers)}

    authors_linked = 0
    authors_created = 0
    papers_failed = 0

    print(f"  S2 returned {len(batch_results)} results, processing DB upserts...")

    # One session per paper: pool_pre_ping=True on the engine handles stale
    # connections transparently, so each database_session() is resilient to
    # transient DNS/connection failures without manual reconnect logic.
    for i, s2_result in enumerate(batch_results):
        paper = arxiv_to_paper.get(s2_result.arxiv_id)
        if not paper:
            continue

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{len(batch_results)} papers processed ({authors_linked} linked, {authors_created} created)")

        try:
            with database_session() as session:
                seen_author_ids = set()  # S2 can return duplicate authors per paper
                for order, s2_author in enumerate(s2_result.authors, start=1):
                    # Upsert author: create if new s2_author_id, skip if exists
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
                        authors_created += 1

                    if author_id in seen_author_ids:
                        continue
                    seen_author_ids.add(author_id)

                    # Create junction row (skip if already exists)
                    existing_link = session.query(PaperAuthorRecord).filter(
                        PaperAuthorRecord.paper_id == paper["id"],
                        PaperAuthorRecord.author_id == author_id,
                    ).first()

                    if not existing_link:
                        session.add(PaperAuthorRecord(
                            paper_id=paper["id"],
                            author_id=author_id,
                            author_order=order,
                        ))
                        authors_linked += 1
        except Exception as e:
            print(f"  FAIL paper {paper['arxiv_id']}: {e}")
            papers_failed += 1

    return {
        "authors_linked": authors_linked,
        "authors_created": authors_created,
        "papers_failed": papers_failed,
    }


def refresh_author_stats(stale_days: int = STALE_DAYS) -> Dict[str, int]:
    """
    Fetch stats for authors where stats_updated_at is NULL or stale.

    @param stale_days: Number of days after which stats are considered stale
    @returns Dict with refreshed and failed counts
    """
    from shared.semantic_scholar.client import fetch_author_stats

    cutoff = datetime.utcnow() - timedelta(days=stale_days)
    refreshed = 0
    failed = 0

    with database_session() as session:
        stale_authors = session.query(AuthorRecord).filter(
            (AuthorRecord.stats_updated_at.is_(None)) |
            (AuthorRecord.stats_updated_at < cutoff)
        ).limit(500).all()

        author_ids = [(a.id, a.s2_author_id) for a in stale_authors]

    print(f"  Found {len(author_ids)} authors needing stats refresh")

    for idx, (author_db_id, s2_id) in enumerate(author_ids):
        if (idx + 1) % 50 == 0:
            print(f"  Stats progress: {idx + 1}/{len(author_ids)} ({refreshed} refreshed, {failed} failed)")

        try:
            stats = fetch_author_stats(s2_id)
            with database_session() as session:
                record = session.query(AuthorRecord).filter(
                    AuthorRecord.id == author_db_id
                ).first()
                if record:
                    record.name = stats.name
                    record.affiliations = stats.affiliations
                    record.homepage = stats.homepage
                    record.paper_count = stats.paper_count
                    record.citation_count = stats.citation_count
                    record.h_index = stats.h_index
                    record.stats_updated_at = datetime.utcnow()
            refreshed += 1
        except Exception as e:
            print(f"  FAIL author {s2_id}: {e}")
            failed += 1

    return {"refreshed": refreshed, "failed": failed}


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id="backfill_author_stats",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time", "authors"],
    doc_md="""
    ### Backfill Author Stats DAG

    **ONE-TIME USE DAG**: Populates the `authors` and `paper_authors` tables
    for all existing papers using the Semantic Scholar batch API.
    Uses /paper/batch (up to 500 papers per request) to minimize API calls.
    """,
)
def backfill_author_stats_dag():

    @task
    def process_all_papers() -> Dict[str, int]:
        """
        Batch-link authors for all papers, then refresh stats.

        @returns Dict with total counts
        """
        total_papers = 0
        total_linked = 0
        total_created = 0
        total_failed = 0

        # Phase 1: Link paper authors using batch endpoint
        while True:
            papers = fetch_papers_without_author_links(batch_size=BATCH_SIZE)
            if not papers:
                break

            total_papers += len(papers)
            print(f"Fetched batch of {len(papers)} papers (total so far: {total_papers})")

            result = link_batch_authors(papers)
            total_linked += result["authors_linked"]
            total_created += result["authors_created"]
            total_failed += result["papers_failed"]

            print(f"  Linked {result['authors_linked']} authors, created {result['authors_created']} new")

        # Phase 2: Refresh author stats
        print("\nRefreshing author stats...")
        stats_result = refresh_author_stats(stale_days=STALE_DAYS)

        print("\n" + "=" * 50)
        print("BACKFILL AUTHOR STATS REPORT")
        print("=" * 50)
        print(f"Papers processed:    {total_papers}")
        print(f"Authors linked:      {total_linked}")
        print(f"Authors created:     {total_created}")
        print(f"Papers failed:       {total_failed}")
        print(f"Stats refreshed:     {stats_result['refreshed']}")
        print(f"Stats refresh failed:{stats_result['failed']}")
        print("=" * 50)

        return {
            "total_papers": total_papers,
            "authors_linked": total_linked,
            "authors_created": total_created,
            "papers_failed": total_failed,
            "stats_refreshed": stats_result["refreshed"],
            "stats_refresh_failed": stats_result["failed"],
        }

    process_all_papers()


backfill_author_stats_dag()
