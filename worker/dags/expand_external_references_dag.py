"""
Expand external references DAG -- fetches references for external citation nodes.

Runs weekly on Monday at 08:00 UTC (3 hours before the daily citation graph DAG).
External nodes are papers that appear as cited_s2_id in paper_citations but have
never been fetched as a source (i.e., they have no outgoing edges in the graph).

Responsibilities:
- Identify external nodes needing reference expansion (LEFT JOIN pattern)
- Batch-fetch their references from Semantic Scholar
- Store new citation edges with INSERT ON CONFLICT DO NOTHING
- Insert sentinel rows for external papers with 0 references
"""

import sys
import pendulum
from typing import Dict, List

from airflow.decorators import dag, task
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from dags.citation_helpers import database_session, fetch_and_store_references

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def fetch_external_nodes_needing_references(session: Session) -> List[str]:
    """
    Find s2_paper_ids that appear as cited_s2_id but NOT as source_s2_id
    in paper_citations. Uses LEFT JOIN for performance on large tables.
    Excludes sentinel rows (source entries with cited_s2_id IS NULL).

    @param session: SQLAlchemy session
    @returns List of s2_paper_ids for external nodes needing reference fetching
    """
    query = text("""
        SELECT DISTINCT cited.cited_s2_id
        FROM paper_citations cited
        LEFT JOIN paper_citations source
            ON source.source_s2_id = cited.cited_s2_id
        WHERE cited.cited_s2_id IS NOT NULL
          AND source.source_s2_id IS NULL
    """)
    rows = session.execute(query).fetchall()
    return [row[0] for row in rows]


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id='expand_external_references',
    start_date=pendulum.datetime(2026, 4, 2, tz='UTC'),
    schedule='0 8 * * 1',  # Weekly on Monday at 08:00 UTC
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'citation-graph', 'expansion', 'weekly'],
    doc_md="""
    ### Expand External References DAG

    Fetches references for external nodes in the citation graph -- papers
    that are cited by our papers but whose own references haven't been
    fetched yet. Runs weekly on Mondays, 3 hours before the daily
    PageRank computation.
    """,
)
def expand_external_references_dag():

    @task
    def expand_external() -> Dict[str, int]:
        """
        Find external nodes and fetch their references from S2.

        @returns Dict with edges_inserted, sentinel_rows, errors counts
        """
        with database_session() as session:
            external_ids = fetch_external_nodes_needing_references(session)

        total = len(external_ids)
        print(f'Found {total} external nodes needing reference expansion')

        if total == 0:
            print('No external nodes to expand.')
            return {'edges_inserted': 0, 'sentinel_rows': 0, 'errors': 0, 'batches_processed': 0}

        with database_session() as session:
            counts = fetch_and_store_references(session, external_ids)

        # Summary
        print('\n' + '=' * 50)
        print('EXTERNAL EXPANSION REPORT')
        print('=' * 50)
        print(f'External nodes:    {total}')
        print(f'Edges inserted:    {counts["edges_inserted"]}')
        print(f'Sentinel rows:     {counts["sentinel_rows"]}')
        print(f'Batches processed: {counts["batches_processed"]}')
        print(f'Batch errors:      {counts["errors"]}')
        print('=' * 50)

        return counts

    expand_external()


expand_external_references_dag()
