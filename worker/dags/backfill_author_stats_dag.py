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


def fetch_papers_without_author_links(batch_size: int = BATCH_SIZE, exclude_ids: set = None) -> List[Dict]:
    """
    Query papers with arxiv_id that have no entries in paper_authors.

    @param batch_size: Maximum number of papers to fetch
    @param exclude_ids: Paper IDs to skip (already attempted, even if failed)
    @returns List of dicts with paper id, paper_uuid, and arxiv_id
    """
    with database_session() as session:
        query = session.query(
            PaperRecord.id,
            PaperRecord.paper_uuid,
            PaperRecord.arxiv_id,
        ).filter(
            PaperRecord.arxiv_id.isnot(None),
            ~PaperRecord.id.in_(
                session.query(PaperAuthorRecord.paper_id).distinct()
            ),
        )
        if exclude_ids:
            query = query.filter(~PaperRecord.id.in_(exclude_ids))
        rows = query.order_by(PaperRecord.id.desc()).limit(batch_size).all()

        return [
            {"id": row.id, "paper_uuid": row.paper_uuid, "arxiv_id": row.arxiv_id}
            for row in rows
        ]


def fetch_papers_missing_signals(batch_size: int = BATCH_SIZE) -> List[int]:
    """
    Query papers that have author links but are missing max_author_h_index in signals.
    These are papers where linking succeeded but stats/signals weren't written yet.

    @param batch_size: Maximum number of paper IDs to fetch
    @returns List of paper IDs
    """
    from sqlalchemy import text

    with database_session() as session:
        rows = session.execute(text("""
            SELECT DISTINCT pa.paper_id
            FROM paper_authors pa
            JOIN papers p ON p.id = pa.paper_id
            WHERE p.signals IS NULL
               OR NOT (p.signals ? 'max_author_h_index')
            ORDER BY pa.paper_id DESC
            LIMIT :limit
        """), {"limit": batch_size}).fetchall()

        return [row[0] for row in rows]


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
    all_author_ids: set = set()

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

                    all_author_ids.add(author_id)

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
        "author_ids": all_author_ids,
    }


def refresh_author_stats(stale_days: int = STALE_DAYS, only_author_ids: set = None) -> Dict[str, int]:
    """
    Batch-fetch stats for authors where stats_updated_at is NULL or stale.
    Uses POST /author/batch (up to 1000 per request) instead of individual calls.

    @param stale_days: Number of days after which stats are considered stale
    @param only_author_ids: If provided, only refresh these author IDs
    @returns Dict with refreshed and failed counts
    """
    from shared.semantic_scholar.client import fetch_author_stats_batch

    cutoff = datetime.utcnow() - timedelta(days=stale_days)
    refreshed = 0
    failed = 0

    with database_session() as session:
        query = session.query(AuthorRecord).filter(
            (AuthorRecord.stats_updated_at.is_(None)) |
            (AuthorRecord.stats_updated_at < cutoff)
        )
        if only_author_ids:
            query = query.filter(AuthorRecord.id.in_(only_author_ids))
        stale_authors = query.limit(1000).all()

        # Map s2_author_id -> db id for updating after batch fetch
        s2_to_db = {a.s2_author_id: a.id for a in stale_authors}

    s2_ids = list(s2_to_db.keys())
    print(f"  Found {len(s2_ids)} authors needing stats refresh")

    if not s2_ids:
        return {"refreshed": 0, "failed": 0}

    try:
        batch_results = fetch_author_stats_batch(s2_ids)
    except Exception as e:
        print(f"  Batch author stats fetch failed: {e}")
        return {"refreshed": 0, "failed": len(s2_ids)}

    print(f"  S2 returned stats for {len(batch_results)} authors")

    for stats in batch_results:
        db_id = s2_to_db.get(stats.s2_author_id)
        if not db_id:
            continue
        try:
            with database_session() as session:
                record = session.query(AuthorRecord).filter(
                    AuthorRecord.id == db_id
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
            print(f"  FAIL saving author {stats.s2_author_id}: {e}")
            failed += 1

    # Count authors that S2 didn't return (not found)
    returned_ids = {s.s2_author_id for s in batch_results}
    not_found = len(s2_ids) - len(returned_ids)
    if not_found:
        print(f"  {not_found} authors not found in S2")
        failed += not_found

    return {"refreshed": refreshed, "failed": failed}


def update_paper_signals(only_paper_ids: set = None) -> Dict[str, int]:
    """
    Compute max_author_h_index for each paper and write it into the signals JSONB column.

    @param only_paper_ids: If provided, only update these paper IDs
    @returns Dict with updated and failed counts
    """
    from sqlalchemy import func

    updated = 0
    failed = 0

    # Fetch max h-index per paper in one query
    with database_session() as session:
        query = session.query(
            PaperAuthorRecord.paper_id,
            func.max(AuthorRecord.h_index).label("max_h_index"),
        ).join(
            AuthorRecord, PaperAuthorRecord.author_id == AuthorRecord.id
        ).filter(
            AuthorRecord.h_index.isnot(None)
        )
        if only_paper_ids:
            query = query.filter(PaperAuthorRecord.paper_id.in_(only_paper_ids))
        rows = query.group_by(
            PaperAuthorRecord.paper_id
        ).all()

        paper_h_index_map = {row.paper_id: row.max_h_index for row in rows}

    print(f"  Found {len(paper_h_index_map)} papers with author h-index data")

    # Update each paper's signals column
    for paper_id, max_h_index in paper_h_index_map.items():
        try:
            with database_session() as session:
                paper = session.query(PaperRecord).filter(
                    PaperRecord.id == paper_id
                ).first()
                if paper:
                    existing_signals = paper.signals or {}
                    existing_signals["max_author_h_index"] = max_h_index
                    paper.signals = existing_signals
                    updated += 1
        except Exception as e:
            print(f"  FAIL paper_id {paper_id}: {e}")
            failed += 1

    return {"updated": updated, "failed": failed}


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
        For each batch: link authors, fetch their stats, and update paper signals
        immediately — so papers get scored as we go instead of waiting for all
        linking to finish first.

        @returns Dict with total counts
        """
        total_papers = 0
        total_linked = 0
        total_created = 0
        total_failed = 0
        total_stats_refreshed = 0
        total_stats_failed = 0
        total_signals_updated = 0
        total_signals_failed = 0
        attempted_paper_ids: set = set()

        batch_num = 0
        while True:
            papers = fetch_papers_without_author_links(batch_size=BATCH_SIZE, exclude_ids=attempted_paper_ids)
            if not papers:
                break

            batch_num += 1
            batch_paper_ids = {p["id"] for p in papers}
            for p in papers:
                attempted_paper_ids.add(p["id"])

            total_papers += len(papers)
            print(f"\n{'=' * 50}")
            print(f"BATCH {batch_num}: {len(papers)} papers (total so far: {total_papers})")
            print(f"{'=' * 50}")

            # Step 1: Link authors
            result = link_batch_authors(papers)
            total_linked += result["authors_linked"]
            total_created += result["authors_created"]
            total_failed += result["papers_failed"]
            print(f"  Linked {result['authors_linked']} authors, created {result['authors_created']} new")

            # Step 2: Refresh stats for authors we just touched
            batch_author_ids = result.get("author_ids", set())
            if batch_author_ids:
                print(f"  Refreshing stats for {len(batch_author_ids)} authors...")
                stats_result = refresh_author_stats(stale_days=STALE_DAYS, only_author_ids=batch_author_ids)
                total_stats_refreshed += stats_result["refreshed"]
                total_stats_failed += stats_result["failed"]
                print(f"  Stats: {stats_result['refreshed']} refreshed, {stats_result['failed']} failed")

            # Step 3: Update signals for papers in this batch
            print(f"  Updating signals for {len(batch_paper_ids)} papers...")
            signals_result = update_paper_signals(only_paper_ids=batch_paper_ids)
            total_signals_updated += signals_result["updated"]
            total_signals_failed += signals_result["failed"]
            print(f"  Signals: {signals_result['updated']} updated, {signals_result['failed']} failed")

        # Catch-up pass: papers that have author links but missing signals
        # (e.g. from a previous run that crashed after linking but before stats/signals)
        missing = fetch_papers_missing_signals(batch_size=BATCH_SIZE)
        if missing:
            print(f"\n{'=' * 50}")
            print(f"CATCH-UP: {len(missing)} papers with authors but missing signals")
            print(f"{'=' * 50}")

            # Collect all author IDs for these papers
            with database_session() as session:
                author_rows = session.query(
                    PaperAuthorRecord.author_id
                ).filter(
                    PaperAuthorRecord.paper_id.in_(missing)
                ).distinct().all()
                catchup_author_ids = {row.author_id for row in author_rows}

            if catchup_author_ids:
                print(f"  Refreshing stats for {len(catchup_author_ids)} authors...")
                stats_result = refresh_author_stats(stale_days=STALE_DAYS, only_author_ids=catchup_author_ids)
                total_stats_refreshed += stats_result["refreshed"]
                total_stats_failed += stats_result["failed"]
                print(f"  Stats: {stats_result['refreshed']} refreshed, {stats_result['failed']} failed")

            print(f"  Updating signals for {len(missing)} papers...")
            signals_result = update_paper_signals(only_paper_ids=set(missing))
            total_signals_updated += signals_result["updated"]
            total_signals_failed += signals_result["failed"]
            print(f"  Signals: {signals_result['updated']} updated, {signals_result['failed']} failed")

        print(f"\n{'=' * 50}")
        print("BACKFILL AUTHOR STATS REPORT")
        print(f"{'=' * 50}")
        print(f"Papers processed:    {total_papers}")
        print(f"Authors linked:      {total_linked}")
        print(f"Authors created:     {total_created}")
        print(f"Papers failed:       {total_failed}")
        print(f"Stats refreshed:     {total_stats_refreshed}")
        print(f"Stats refresh failed:{total_stats_failed}")
        print(f"Signals updated:     {total_signals_updated}")
        print(f"Signals failed:      {total_signals_failed}")
        print(f"{'=' * 50}")

        return {
            "total_papers": total_papers,
            "authors_linked": total_linked,
            "authors_created": total_created,
            "papers_failed": total_failed,
            "stats_refreshed": total_stats_refreshed,
            "stats_refresh_failed": total_stats_failed,
            "signals_updated": total_signals_updated,
            "signals_failed": total_signals_failed,
        }

    process_all_papers()


backfill_author_stats_dag()
