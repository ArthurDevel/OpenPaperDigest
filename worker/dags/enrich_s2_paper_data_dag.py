"""
S2 paper data enrichment DAG -- owns Semantic Scholar-derived paper state.

Runs daily at 10:00 UTC with four chained tasks:
1. process_all_papers: enrich papers with S2 metadata (s2_ids, metrics, etc.)
2. sync_author_links: create/update author links for enriched papers
3. refresh_author_stats_task: refresh Semantic Scholar author stats
4. refresh_paper_signals_task: recompute paper signals derived from authors

Responsibilities:
- Query papers needing S2 enrichment (arxiv_id present, s2_ids NULL or empty)
- Retry papers with s2_ids = {} that are 1-7 days old (S2 may not have indexed them on first attempt)
- Batch-fetch metadata from Semantic Scholar (500 papers per API call)
- Update papers with S2 metadata and explicit enrichment progress timestamps
- Link authors only from this DAG
- Refresh author stats only from this DAG
- Refresh author-derived paper signals only from this DAG
"""

import sys
import pendulum
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from airflow.decorators import dag, task
from sqlalchemy import or_, and_, cast, String, func
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from shared.semantic_scholar.client import (
    fetch_author_stats_batch,
    fetch_paper_authors_batch,
    fetch_paper_metadata_batch,
)
from shared.semantic_scholar.models import S2PaperMetadata
from papers.db.models import PaperRecord, AuthorRecord, PaperAuthorRecord

# ============================================================================
# CONSTANTS
# ============================================================================

BATCH_SIZE = 500
STALE_DAYS = 7


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


RETRY_WINDOW_DAYS = 7


def fetch_papers_needing_s2_data(exclude_ids: List[str] = None) -> List[Tuple[int, str]]:
    """
    Query papers that have an arxiv_id but no S2 data yet, plus papers where
    S2 returned no match on the first attempt (s2_ids = {}) that are between
    1 and 7 days old. Papers older than 7 days with s2_ids = {} are assumed
    to be genuinely absent from S2 and are not retried.

    @param exclude_ids: arXiv IDs to exclude (e.g. failed in current run)
    @returns List of (paper_id, arxiv_id) tuples
    """
    now = datetime.utcnow()
    retry_min_age = now - timedelta(days=1)
    retry_max_age = now - timedelta(days=RETRY_WINDOW_DAYS)

    with database_session() as session:
        query = session.query(PaperRecord.id, PaperRecord.arxiv_id).filter(
            PaperRecord.arxiv_id.isnot(None),
            or_(
                PaperRecord.s2_ids.is_(None),
                and_(
                    cast(PaperRecord.s2_ids, String) == '{}',
                    PaperRecord.created_at < retry_min_age,
                    PaperRecord.created_at > retry_max_age,
                ),
            ),
        )

        if exclude_ids:
            query = query.filter(PaperRecord.arxiv_id.notin_(exclude_ids))

        rows = query.order_by(PaperRecord.id.desc()).all()
        return [(row.id, row.arxiv_id) for row in rows]


def build_classification_dict(paper_record: PaperRecord, s2_metadata: S2PaperMetadata) -> dict:
    """
    Merge S2 classification data into existing classification JSONB.
    Preserves existing arxiv_* keys, adds/overwrites s2_* keys.

    @param paper_record: PaperRecord with existing classification (or None)
    @param s2_metadata: S2PaperMetadata with fields of study and publication types
    @returns Merged classification dict
    """
    result = dict(paper_record.classification or {})

    # Add S2 fields of study
    if s2_metadata.s2_fields_of_study:
        result['s2_fields_of_study'] = [
            {'category': f.category, 'source': f.source}
            for f in s2_metadata.s2_fields_of_study
        ]

    # Add S2 publication types
    if s2_metadata.publication_types:
        result['s2_publication_types'] = s2_metadata.publication_types

    return result


def enrich_papers_with_s2_data(
    session: Session,
    papers: List[Tuple[int, str]],
    metadata_list: List[S2PaperMetadata],
) -> Dict[str, int]:
    """
    Update paper records with S2 metadata. Papers not found by S2 get s2_ids = {}
    so they are excluded from future enrichment queries.

    @param session: SQLAlchemy session
    @param papers: List of (paper_id, arxiv_id) tuples
    @param metadata_list: S2PaperMetadata DTOs returned from batch fetch
    @returns Dict with enriched, no_match, error counts
    """
    # Build lookup: arxiv_id -> S2PaperMetadata
    metadata_by_arxiv = {m.arxiv_id: m for m in metadata_list if m.arxiv_id}
    attempted_at = datetime.utcnow()

    enriched = 0
    no_match = 0
    errors = 0

    for paper_id, arxiv_id in papers:
        try:
            record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
            if not record:
                continue

            record.s2_last_attempted_at = attempted_at
            s2_meta = metadata_by_arxiv.get(arxiv_id)

            if s2_meta:
                record.s2_ids = s2_meta.to_s2_ids_dict()
                record.s2_metrics = s2_meta.to_s2_metrics_dict()
                record.classification = build_classification_dict(record, s2_meta)
                record.publication_info = s2_meta.to_publication_info_dict()
                record.s2_tldr = s2_meta.tldr
                record.s2_embedding = s2_meta.embedding
                record.s2_enriched_at = attempted_at
                record.s2_enrichment_error = None
                enriched += 1
            else:
                # Empty dict sentinel -- paper may still be retried within the retry window.
                record.s2_ids = {}
                record.s2_enrichment_error = 'No Semantic Scholar match found'
                no_match += 1

        except Exception as e:
            print(f'    ERROR enriching paper {paper_id} ({arxiv_id}): {e}')
            record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
            if record:
                record.s2_last_attempted_at = attempted_at
                record.s2_enrichment_error = str(e)
            errors += 1

    session.commit()

    return {'enriched': enriched, 'no_match': no_match, 'errors': errors}


def mark_s2_batch_failure(papers: List[Tuple[int, str]], error_message: str) -> None:
    """Stamp a failed S2 metadata batch so the paper record reflects the attempt."""
    if not papers:
        return

    paper_ids = [paper_id for paper_id, _ in papers]
    attempted_at = datetime.utcnow()

    with database_session() as session:
        records = session.query(PaperRecord).filter(PaperRecord.id.in_(paper_ids)).all()
        for record in records:
            record.s2_last_attempted_at = attempted_at
            record.s2_enrichment_error = error_message


def fetch_papers_needing_author_sync() -> List[Tuple[int, str]]:
    """
    Query papers that have S2 IDs but have not yet had author linking synced
    by the enrichment DAG.

    @returns List of (paper_id, arxiv_id) tuples
    """
    with database_session() as session:
        rows = session.query(PaperRecord.id, PaperRecord.arxiv_id).filter(
            PaperRecord.arxiv_id.isnot(None),
            PaperRecord.s2_ids.isnot(None),
            cast(PaperRecord.s2_ids, String) != '{}',
            PaperRecord.author_links_synced_at.is_(None),
        ).order_by(PaperRecord.id.desc()).all()

        return [(row.id, row.arxiv_id) for row in rows]


def link_authors_for_papers(papers: List[Tuple[int, str]]) -> Dict[str, int]:
    """
    Batch-fetch authors from S2 and create paper_authors + authors records.
    Processes in BATCH_SIZE chunks.

    @param papers: List of (paper_id, arxiv_id) tuples
    @returns Dict with authors_linked, authors_created, papers_skipped counts
    """
    total_linked = 0
    total_created = 0
    total_skipped = 0
    total_synced = 0
    author_ids_touched = set()

    for i in range(0, len(papers), BATCH_SIZE):
        batch = papers[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        print(f'\n  Batch {batch_num}: linking authors for {len(batch)} papers...')

        arxiv_ids = [arxiv_id for _, arxiv_id in batch]
        id_by_arxiv = {arxiv_id: paper_id for paper_id, arxiv_id in batch}

        try:
            batch_results = fetch_paper_authors_batch(arxiv_ids)
        except Exception as e:
            print(f'    S2 batch call failed: {e}')
            total_skipped += len(batch)
            with database_session() as session:
                attempted_at = datetime.utcnow()
                for paper_id, _ in batch:
                    record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
                    if record:
                        record.s2_enrichment_error = f'Author sync failed: {e}'
                        record.s2_last_attempted_at = attempted_at
            continue

        returned_arxiv_ids = set()
        for s2_result in batch_results:
            paper_id = id_by_arxiv.get(s2_result.arxiv_id)
            if not paper_id:
                continue
            returned_arxiv_ids.add(s2_result.arxiv_id)

            try:
                with database_session() as session:
                    paper_record = session.query(PaperRecord).filter(
                        PaperRecord.id == paper_id
                    ).first()
                    if not paper_record:
                        continue

                    seen_author_ids = set()
                    for order, s2_author in enumerate(s2_result.authors, start=1):
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
                            total_created += 1

                        author_ids_touched.add(author_id)
                        if author_id in seen_author_ids:
                            continue
                        seen_author_ids.add(author_id)

                        existing_link = session.query(PaperAuthorRecord).filter(
                            PaperAuthorRecord.paper_id == paper_id,
                            PaperAuthorRecord.author_id == author_id,
                        ).first()

                        if not existing_link:
                            session.add(PaperAuthorRecord(
                                paper_id=paper_id,
                                author_id=author_id,
                                author_order=order,
                            ))
                            total_linked += 1
                    paper_record.author_links_synced_at = datetime.utcnow()
                    paper_record.s2_enrichment_error = None
                    total_synced += 1
            except Exception as e:
                print(f'    FAIL paper {paper_id} ({s2_result.arxiv_id}): {e}')
                with database_session() as session:
                    record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
                    if record:
                        record.s2_enrichment_error = f'Author sync failed: {e}'
                total_skipped += 1

        missing_ids = set(arxiv_ids) - returned_arxiv_ids
        if missing_ids:
            total_skipped += len(missing_ids)
            with database_session() as session:
                attempted_at = datetime.utcnow()
                for arxiv_id in missing_ids:
                    paper_id = id_by_arxiv.get(arxiv_id)
                    if paper_id is None:
                        continue
                    record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
                    if record:
                        record.s2_last_attempted_at = attempted_at
                        record.s2_enrichment_error = 'Author sync returned no result'

        print(f'    Linked: {total_linked}, Created: {total_created}')

    return {
        'authors_linked': total_linked,
        'authors_created': total_created,
        'papers_skipped': total_skipped,
        'papers_synced': total_synced,
        'authors_touched': len(author_ids_touched),
    }


def refresh_author_stats(stale_days: int = STALE_DAYS, only_author_ids: Optional[set] = None) -> Dict[str, int]:
    """
    Refresh author stats for authors with missing or stale data.

    @param stale_days: Number of days after which stats are considered stale
    @param only_author_ids: If provided, only refresh these author IDs
    @returns Dict with refreshed and failed counts
    """
    cutoff = datetime.utcnow() - timedelta(days=stale_days)
    refreshed = 0
    failed = 0

    while True:
        with database_session() as session:
            query = session.query(AuthorRecord).filter(
                (AuthorRecord.stats_updated_at.is_(None)) |
                (AuthorRecord.stats_updated_at < cutoff)
            )
            if only_author_ids:
                query = query.filter(AuthorRecord.id.in_(only_author_ids))
            stale_authors = query.limit(1000).all()
            s2_to_db = {author.s2_author_id: author.id for author in stale_authors}

        if not s2_to_db:
            break

        s2_ids = list(s2_to_db.keys())
        print(f'  Fetching stats for {len(s2_ids)} authors...')

        try:
            batch_results = fetch_author_stats_batch(s2_ids)
        except Exception as e:
            print(f'  Batch author stats fetch failed: {e}')
            failed += len(s2_ids)
            break

        returned_ids = set()
        for stats in batch_results:
            returned_ids.add(stats.s2_author_id)
            db_id = s2_to_db.get(stats.s2_author_id)
            if not db_id:
                continue
            try:
                with database_session() as session:
                    record = session.query(AuthorRecord).filter(AuthorRecord.id == db_id).first()
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
                print(f'  FAIL saving author {stats.s2_author_id}: {e}')
                failed += 1

        missing_ids = set(s2_ids) - returned_ids
        if missing_ids:
            failed += len(missing_ids)
            with database_session() as session:
                for s2_id in missing_ids:
                    db_id = s2_to_db.get(s2_id)
                    if not db_id:
                        continue
                    record = session.query(AuthorRecord).filter(AuthorRecord.id == db_id).first()
                    if record:
                        record.stats_updated_at = datetime.utcnow()

        if only_author_ids:
            break

    return {'refreshed': refreshed, 'failed': failed}


def fetch_papers_needing_signal_refresh() -> List[int]:
    """
    Query papers whose author-derived signals are missing or older than the
    latest author stats update.

    @returns List of paper IDs needing signal refresh
    """
    with database_session() as session:
        rows = session.query(
            PaperRecord.id,
        ).join(
            PaperAuthorRecord, PaperAuthorRecord.paper_id == PaperRecord.id
        ).join(
            AuthorRecord, AuthorRecord.id == PaperAuthorRecord.author_id
        ).filter(
            PaperRecord.author_links_synced_at.isnot(None),
            or_(
                PaperRecord.signals_refreshed_at.is_(None),
                AuthorRecord.stats_updated_at.is_(None),
                AuthorRecord.stats_updated_at > PaperRecord.signals_refreshed_at,
            ),
        ).distinct().order_by(PaperRecord.id.desc()).all()

        return [row[0] for row in rows]


def refresh_paper_signals(paper_ids: List[int]) -> Dict[str, int]:
    """
    Compute and persist `max_author_h_index` for the given papers.

    A paper is still stamped as refreshed even when none of its linked authors
    currently have an h-index, which prevents infinite retries for papers with
    legitimately missing author metrics.
    """
    if not paper_ids:
        return {'updated': 0, 'failed': 0}

    with database_session() as session:
        rows = session.query(
            PaperAuthorRecord.paper_id,
            func.max(AuthorRecord.h_index).label('max_h_index'),
        ).join(
            AuthorRecord, PaperAuthorRecord.author_id == AuthorRecord.id
        ).filter(
            PaperAuthorRecord.paper_id.in_(paper_ids),
            AuthorRecord.h_index.isnot(None),
        ).group_by(
            PaperAuthorRecord.paper_id
        ).all()

        max_h_index_by_paper = {row.paper_id: row.max_h_index for row in rows}
        papers = session.query(PaperRecord).filter(PaperRecord.id.in_(paper_ids)).all()

        refreshed_at = datetime.utcnow()
        for paper in papers:
            signals = dict(paper.signals or {})
            max_h_index = max_h_index_by_paper.get(paper.id)
            if max_h_index is None:
                signals.pop('max_author_h_index', None)
            else:
                signals['max_author_h_index'] = max_h_index
            paper.signals = signals
            paper.signals_refreshed_at = refreshed_at
            if paper.s2_enrichment_error and paper.s2_enrichment_error.startswith('Signal refresh failed'):
                paper.s2_enrichment_error = None

    return {'updated': len(paper_ids), 'failed': 0}


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id='enrich_s2_paper_data',
    start_date=pendulum.datetime(2026, 3, 24, tz='UTC'),
    schedule='0 10 * * *',  # Daily at 10:00 UTC
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'enrichment', 'semantic-scholar', 'daily'],
    doc_md="""
    ### S2 Paper Data Enrichment DAG

    Four chained tasks:
    1. **process_all_papers**: Enriches papers with S2 metadata (s2_ids, metrics, etc.)
    2. **sync_author_links**: Links authors for papers whose S2 metadata is ready
    3. **refresh_author_stats_task**: Refreshes author h-index and citation stats
    4. **refresh_paper_signals_task**: Recomputes paper signals derived from authors
    """,
)
def enrich_s2_paper_data_dag():

    @task
    def process_all_papers() -> Dict[str, int]:
        """
        Main task: fetch papers needing enrichment, process in batches of 500.

        @returns Dict with total enriched/no_match/error counts
        """
        papers = fetch_papers_needing_s2_data()
        total = len(papers)
        print(f'Found {total} papers needing S2 enrichment')

        if total == 0:
            print('Nothing to enrich.')
            return {'enriched': 0, 'no_match': 0, 'errors': 0}

        total_enriched = 0
        total_no_match = 0
        total_errors = 0

        # Process in batches of BATCH_SIZE
        for i in range(0, total, BATCH_SIZE):
            batch = papers[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            print(f'\nBatch {batch_num}: processing {len(batch)} papers...')

            arxiv_ids = [arxiv_id for _, arxiv_id in batch]

            try:
                metadata_list = fetch_paper_metadata_batch(arxiv_ids)
                print(f'  S2 returned {len(metadata_list)} matches for {len(arxiv_ids)} papers')
            except Exception as e:
                print(f'  S2 batch fetch FAILED: {e}')
                mark_s2_batch_failure(batch, f'S2 metadata fetch failed: {e}')
                total_errors += len(batch)
                continue

            with database_session() as session:
                counts = enrich_papers_with_s2_data(session, batch, metadata_list)

            total_enriched += counts['enriched']
            total_no_match += counts['no_match']
            total_errors += counts['errors']

            print(f'  Enriched: {counts["enriched"]}, No match: {counts["no_match"]}, Errors: {counts["errors"]}')

        # Summary report
        print('\n' + '=' * 50)
        print('S2 ENRICHMENT REPORT')
        print('=' * 50)
        print(f'Total papers queried:  {total}')
        print(f'Enriched:              {total_enriched}')
        print(f'No S2 match:           {total_no_match}')
        print(f'Errors:                {total_errors}')
        print('=' * 50)

        return {
            'enriched': total_enriched,
            'no_match': total_no_match,
            'errors': total_errors,
        }

    @task
    def sync_author_links() -> Dict[str, int]:
        """
        Find papers whose S2 metadata is ready and sync their author links.

        @returns Dict with authors_linked, authors_created, papers_skipped counts
        """
        papers = fetch_papers_needing_author_sync()
        total = len(papers)
        print(f'Found {total} papers needing author sync')

        if total == 0:
            print('No papers need author sync.')
            return {
                'authors_linked': 0,
                'authors_created': 0,
                'papers_skipped': 0,
                'papers_synced': 0,
                'authors_touched': 0,
            }

        counts = link_authors_for_papers(papers)

        print('\n' + '=' * 50)
        print('AUTHOR SYNC REPORT')
        print('=' * 50)
        print(f'Papers queried:    {total}')
        print(f'Authors linked:    {counts["authors_linked"]}')
        print(f'Authors created:   {counts["authors_created"]}')
        print(f'Papers synced:     {counts["papers_synced"]}')
        print(f'Papers skipped:    {counts["papers_skipped"]}')
        print('=' * 50)

        return counts

    @task
    def refresh_author_stats_task() -> Dict[str, int]:
        """
        Refresh stale or missing Semantic Scholar author stats.
        """
        counts = refresh_author_stats()

        print('\n' + '=' * 50)
        print('AUTHOR STATS REPORT')
        print('=' * 50)
        print(f'Authors refreshed: {counts["refreshed"]}')
        print(f'Authors failed:    {counts["failed"]}')
        print('=' * 50)

        return counts

    @task
    def refresh_paper_signals_task() -> Dict[str, int]:
        """
        Refresh author-derived paper signals after metadata and stats sync.
        """
        paper_ids = fetch_papers_needing_signal_refresh()
        total = len(paper_ids)
        print(f'Found {total} papers needing signal refresh')

        if total == 0:
            print('No papers need signal refresh.')
            return {'updated': 0, 'failed': 0}

        counts = refresh_paper_signals(paper_ids)

        print('\n' + '=' * 50)
        print('PAPER SIGNAL REPORT')
        print('=' * 50)
        print(f'Papers refreshed:  {counts["updated"]}')
        print(f'Papers failed:     {counts["failed"]}')
        print('=' * 50)

        return counts

    process_all_papers() >> sync_author_links() >> refresh_author_stats_task() >> refresh_paper_signals_task()


enrich_s2_paper_data_dag()
