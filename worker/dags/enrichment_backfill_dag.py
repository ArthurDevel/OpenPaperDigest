"""
Manual backfill for the enrichment domain.

This DAG repairs Semantic Scholar-owned state only:
- paper S2 metadata
- author links
- author stats
- author-derived paper signals
"""

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pendulum
from airflow.decorators import dag, task
from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from papers.db.models import AuthorRecord, PaperAuthorRecord, PaperRecord
from shared.db import SessionLocal
from shared.semantic_scholar.client import (
    fetch_author_stats_batch,
    fetch_paper_authors_batch,
    fetch_paper_metadata_batch,
)
from shared.semantic_scholar.models import S2PaperMetadata


BATCH_SIZE = 500
STALE_DAYS = 7


@contextmanager
def database_session():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def build_classification_dict(paper_record: PaperRecord, s2_metadata: S2PaperMetadata) -> dict:
    """Merge S2 classification data into the existing paper classification JSON."""
    result = dict(paper_record.classification or {})
    if s2_metadata.s2_fields_of_study:
        result['s2_fields_of_study'] = [
            {'category': field.category, 'source': field.source}
            for field in s2_metadata.s2_fields_of_study
        ]
    if s2_metadata.publication_types:
        result['s2_publication_types'] = s2_metadata.publication_types
    return result


def enrich_papers_with_s2_data(
    session: Session,
    papers: List[Tuple[int, str]],
    metadata_list: List[S2PaperMetadata],
) -> Dict[str, int]:
    """Apply a fetched S2 metadata batch to paper rows."""
    metadata_by_arxiv = {metadata.arxiv_id: metadata for metadata in metadata_list if metadata.arxiv_id}
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
                record.s2_ids = {}
                record.s2_enrichment_error = 'No Semantic Scholar match found'
                no_match += 1
        except Exception as exc:
            print(f'  FAIL S2 metadata {paper_id} ({arxiv_id}): {exc}')
            record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
            if record:
                record.s2_last_attempted_at = attempted_at
                record.s2_enrichment_error = str(exc)
            errors += 1

    session.commit()
    return {'enriched': enriched, 'no_match': no_match, 'errors': errors}


def refresh_author_stats(stale_days: int = STALE_DAYS, only_author_ids: Optional[set] = None) -> Dict[str, int]:
    """Refresh author stats for missing or stale author records."""
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

        try:
            batch_results = fetch_author_stats_batch(list(s2_to_db.keys()))
        except Exception as exc:
            print(f'  FAIL author stats batch: {exc}')
            failed += len(s2_to_db)
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
                    if not record:
                        continue
                    record.name = stats.name
                    record.affiliations = stats.affiliations
                    record.homepage = stats.homepage
                    record.paper_count = stats.paper_count
                    record.citation_count = stats.citation_count
                    record.h_index = stats.h_index
                    record.stats_updated_at = datetime.utcnow()
                    refreshed += 1
            except Exception as exc:
                print(f'  FAIL author stats save {stats.s2_author_id}: {exc}')
                failed += 1

        missing_ids = set(s2_to_db.keys()) - returned_ids
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


def refresh_paper_signals(paper_ids: List[int]) -> Dict[str, int]:
    """Refresh max_author_h_index in batches for the supplied papers."""
    if not paper_ids:
        return {'updated': 0, 'failed': 0}

    updated = 0
    failed = 0

    for i in range(0, len(paper_ids), BATCH_SIZE):
        batch_ids = paper_ids[i:i + BATCH_SIZE]
        try:
            with database_session() as session:
                rows = session.query(
                    PaperAuthorRecord.paper_id,
                    func.max(AuthorRecord.h_index).label('max_h_index'),
                ).join(
                    AuthorRecord, PaperAuthorRecord.author_id == AuthorRecord.id
                ).filter(
                    PaperAuthorRecord.paper_id.in_(batch_ids),
                    AuthorRecord.h_index.isnot(None),
                ).group_by(
                    PaperAuthorRecord.paper_id
                ).all()

                max_h_index_by_paper = {row.paper_id: row.max_h_index for row in rows}
                papers = session.query(PaperRecord).filter(PaperRecord.id.in_(batch_ids)).all()
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
                updated += len(papers)
        except Exception as exc:
            print(f'  FAIL paper signal batch {i // BATCH_SIZE + 1}: {exc}')
            failed += len(batch_ids)
            with database_session() as session:
                records = session.query(PaperRecord).filter(PaperRecord.id.in_(batch_ids)).all()
                for record in records:
                    record.s2_enrichment_error = f'Signal refresh failed: {exc}'

    return {'updated': updated, 'failed': failed}


@dag(
    dag_id='enrichment_backfill',
    start_date=pendulum.datetime(2025, 1, 1, tz='UTC'),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'backfill', 'enrichment'],
    doc_md="""
    ### Enrichment Backfill

    Manual backfill aligned to the enrichment ownership domain. It scans the
    current database for missing or stale S2-derived state and repairs it in
    the same stage order as the scheduled enrichment DAG.
    """,
)
def enrichment_backfill_dag():

    @task
    def backfill_s2_metadata() -> Dict[str, int]:
        with database_session() as session:
            rows = session.query(PaperRecord.id, PaperRecord.arxiv_id).filter(
                PaperRecord.arxiv_id.isnot(None),
                or_(
                    PaperRecord.s2_ids.is_(None),
                    cast(PaperRecord.s2_ids, String) == '{}',
                ),
            ).order_by(PaperRecord.id.asc()).all()

        papers = [(row.id, row.arxiv_id) for row in rows if row.arxiv_id]
        enriched = 0
        no_match = 0
        errors = 0

        for i in range(0, len(papers), BATCH_SIZE):
            batch = papers[i:i + BATCH_SIZE]
            arxiv_ids = [arxiv_id for _, arxiv_id in batch]
            try:
                metadata_list = fetch_paper_metadata_batch(arxiv_ids)
            except Exception as exc:
                attempted_at = datetime.utcnow()
                with database_session() as session:
                    for paper_id, _ in batch:
                        record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
                        if record:
                            record.s2_last_attempted_at = attempted_at
                            record.s2_enrichment_error = f'S2 metadata fetch failed: {exc}'
                errors += len(batch)
                continue

            with database_session() as session:
                counts = enrich_papers_with_s2_data(session, batch, metadata_list)
            enriched += counts['enriched']
            no_match += counts['no_match']
            errors += counts['errors']

        return {'total': len(papers), 'enriched': enriched, 'no_match': no_match, 'errors': errors}

    @task
    def backfill_author_links() -> Dict[str, int]:
        with database_session() as session:
            rows = session.query(PaperRecord.id, PaperRecord.arxiv_id).filter(
                PaperRecord.arxiv_id.isnot(None),
                PaperRecord.s2_ids.isnot(None),
                cast(PaperRecord.s2_ids, String) != '{}',
                PaperRecord.author_links_synced_at.is_(None),
            ).order_by(PaperRecord.id.asc()).all()

        papers = [(row.id, row.arxiv_id) for row in rows if row.arxiv_id]
        total_linked = 0
        total_created = 0
        total_skipped = 0
        total_synced = 0
        author_ids_touched = set()

        for i in range(0, len(papers), BATCH_SIZE):
            batch = papers[i:i + BATCH_SIZE]
            arxiv_ids = [arxiv_id for _, arxiv_id in batch]
            id_by_arxiv = {arxiv_id: paper_id for paper_id, arxiv_id in batch}

            try:
                batch_results = fetch_paper_authors_batch(arxiv_ids)
            except Exception as exc:
                total_skipped += len(batch)
                with database_session() as session:
                    attempted_at = datetime.utcnow()
                    for paper_id, _ in batch:
                        record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
                        if record:
                            record.s2_enrichment_error = f'Author sync failed: {exc}'
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
                        paper_record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
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
                except Exception as exc:
                    print(f'  FAIL author links {paper_id}: {exc}')
                    total_skipped += 1
                    with database_session() as session:
                        record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
                        if record:
                            record.s2_enrichment_error = f'Author sync failed: {exc}'

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

        return {
            'total': len(papers),
            'authors_linked': total_linked,
            'authors_created': total_created,
            'papers_skipped': total_skipped,
            'papers_synced': total_synced,
            'authors_touched': len(author_ids_touched),
        }

    @task
    def backfill_author_stats() -> Dict[str, int]:
        return refresh_author_stats()

    @task
    def backfill_paper_signals() -> Dict[str, int]:
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
            ).distinct().order_by(PaperRecord.id.asc()).all()

        paper_ids = [row[0] for row in rows]
        return {
            'total': len(paper_ids),
            **refresh_paper_signals(paper_ids),
        }

    backfill_s2_metadata() >> backfill_author_links() >> backfill_author_stats() >> backfill_paper_signals()


enrichment_backfill_dag()
