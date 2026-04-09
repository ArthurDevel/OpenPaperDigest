"""
Shared helpers for citation graph DAGs.

Extracted from citation_graph_dag.py to avoid duplicate DAG registration
when expand_external_references_dag.py imports these functions.
"""

import sys
from datetime import datetime
from contextlib import contextmanager
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from shared.semantic_scholar.client import fetch_paper_references_batch

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


def fetch_and_store_references(session: Session, s2_paper_ids: List[str]) -> Dict[str, int]:
    """
    Batch-fetch references from S2 API (500 per batch), INSERT ON CONFLICT
    DO NOTHING into paper_citations. Papers with 0 refs get a sentinel row
    (cited_s2_id=NULL).

    @param session: SQLAlchemy session
    @param s2_paper_ids: List of S2 paper IDs to fetch references for
    @returns Dict with edges_inserted, sentinel_rows, errors, batches_processed counts
    """
    total = len(s2_paper_ids)
    total_edges = 0
    total_sentinels = 0
    total_errors = 0
    batches_processed = 0

    for i in range(0, total, BATCH_SIZE):
        batch = s2_paper_ids[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        print(f'  Batch {batch_num}: fetching references for {len(batch)} papers...')

        try:
            references = fetch_paper_references_batch(batch)

            # Track which source papers returned at least one reference
            sources_with_refs = set()
            for ref in references:
                sources_with_refs.add(ref.source_s2_id)

            # Insert citation edges with ON CONFLICT DO NOTHING
            for ref in references:
                stmt = text("""
                    INSERT INTO paper_citations (source_s2_id, cited_s2_id, is_influential, created_at)
                    VALUES (:source, :cited, :influential, :now)
                    ON CONFLICT DO NOTHING
                """)
                session.execute(stmt, {
                    'source': ref.source_s2_id,
                    'cited': ref.cited_s2_id,
                    'influential': ref.is_influential,
                    'now': datetime.utcnow(),
                })
            total_edges += len(references)

            # Insert sentinel rows for papers with 0 references
            sentinel_count = 0
            for paper_id in batch:
                if paper_id not in sources_with_refs:
                    stmt = text("""
                        INSERT INTO paper_citations (source_s2_id, cited_s2_id, is_influential, created_at)
                        VALUES (:source, NULL, NULL, :now)
                        ON CONFLICT DO NOTHING
                    """)
                    session.execute(stmt, {
                        'source': paper_id,
                        'now': datetime.utcnow(),
                    })
                    sentinel_count += 1

            total_sentinels += sentinel_count
            session.commit()

            print(f'    Edges: {len(references)}, Sentinels: {sentinel_count}')
            batches_processed += 1

        except Exception as e:
            print(f'    ERROR in batch {batch_num}: {e}')
            session.rollback()
            total_errors += 1

    return {
        'edges_inserted': total_edges,
        'sentinel_rows': total_sentinels,
        'errors': total_errors,
        'batches_processed': batches_processed,
    }
