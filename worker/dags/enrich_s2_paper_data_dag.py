"""
S2 paper data enrichment DAG -- enriches papers with Semantic Scholar metadata.

Runs daily at 10:00 UTC. For each paper with an arxiv_id but no S2 data yet,
fetches comprehensive metadata from the S2 batch API and updates the DB.

Responsibilities:
- Query papers needing S2 enrichment (arxiv_id present, s2_ids NULL or empty)
- Retry papers with s2_ids = {} that are 1-7 days old (S2 may not have indexed them on first attempt)
- Batch-fetch metadata from Semantic Scholar (500 papers per API call)
- Update papers with s2_ids, s2_metrics, classification, publication_info, s2_tldr, s2_embedding
- Mark unmatched papers with s2_ids = {} (retried until RETRY_WINDOW_DAYS expires)
"""

import sys
import pendulum
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from airflow.decorators import dag, task
from sqlalchemy import or_, and_, cast, String
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from shared.semantic_scholar.client import fetch_paper_metadata_batch
from shared.semantic_scholar.models import S2PaperMetadata
from papers.db.models import PaperRecord

# ============================================================================
# CONSTANTS
# ============================================================================

BATCH_SIZE = 500


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

    enriched = 0
    no_match = 0
    errors = 0

    for paper_id, arxiv_id in papers:
        try:
            record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
            if not record:
                continue

            s2_meta = metadata_by_arxiv.get(arxiv_id)

            if s2_meta:
                record.s2_ids = s2_meta.to_s2_ids_dict()
                record.s2_metrics = s2_meta.to_s2_metrics_dict()
                record.classification = build_classification_dict(record, s2_meta)
                record.publication_info = s2_meta.to_publication_info_dict()
                record.s2_tldr = s2_meta.tldr
                record.s2_embedding = s2_meta.embedding
                enriched += 1
            else:
                # Empty dict sentinel -- paper won't be retried
                record.s2_ids = {}
                no_match += 1

        except Exception as e:
            print(f'    ERROR enriching paper {paper_id} ({arxiv_id}): {e}')
            errors += 1

    session.commit()

    return {'enriched': enriched, 'no_match': no_match, 'errors': errors}


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

    Enriches papers with comprehensive metadata from Semantic Scholar.
    Processes all papers that have an `arxiv_id` but no `s2_ids` yet,
    in batches of 500 via the S2 batch API.
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

    process_all_papers()


enrich_s2_paper_data_dag()
