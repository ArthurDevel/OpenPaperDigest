"""
Fetch inbound citations DAG -- fetches papers that cite our papers.

Runs weekly on Tuesday at 08:00 UTC. Enriches the citation graph with inbound
edges (currently we only have outbound references from our papers).

Responsibilities:
- Identify papers in the papers table that need inbound citation fetching
- Batch-fetch their inbound citations from Semantic Scholar
- Store new citation edges with bulk INSERT ON CONFLICT DO NOTHING
- Mark processed papers via inbound_citations_fetched_at timestamp
"""

import sys
import pendulum
from typing import Dict, List

from airflow.decorators import dag, task
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from dags.citation_helpers import database_session, fetch_and_store_inbound_citations

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def fetch_papers_needing_inbound_citations(session: Session) -> List[str]:
    """
    Find papers with an s2_paper_id that have not yet had inbound citations fetched.
    Only queries the papers table -- never external nodes.

    @param session: SQLAlchemy session
    @returns List of s2_paper_id strings needing inbound citation fetch
    """
    query = text("""
        SELECT DISTINCT p.s2_ids->>'s2_paper_id' AS s2_paper_id
        FROM papers p
        WHERE p.s2_ids->>'s2_paper_id' IS NOT NULL
          AND p.s2_ids->>'s2_paper_id' != ''
          AND p.inbound_citations_fetched_at IS NULL
    """)
    rows = session.execute(query).fetchall()
    return [row[0] for row in rows]


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id='fetch_inbound_citations',
    start_date=pendulum.datetime(2026, 4, 9, tz='UTC'),
    schedule='0 8 * * 2',  # Weekly on Tuesday at 08:00 UTC
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'citation-graph', 'inbound', 'weekly'],
    doc_md="""
    ### Fetch Inbound Citations DAG

    Fetches papers that cite our papers from Semantic Scholar. Runs weekly
    on Tuesdays, one day after the expand external references DAG. Only
    fetches inbound citations for papers in the papers table (never external
    nodes) to enforce the two-hop boundary.
    """,
)
def fetch_inbound_citations_dag():

    @task
    def fetch_inbound() -> Dict[str, int]:
        """
        Find papers needing inbound citations and fetch them from S2.

        @returns Dict with edges_inserted, papers_marked, errors counts
        """
        with database_session() as session:
            paper_ids = fetch_papers_needing_inbound_citations(session)

        total = len(paper_ids)
        print(f'Found {total} papers needing inbound citation fetch')

        if total == 0:
            print('No papers need inbound citation fetching.')
            return {'edges_inserted': 0, 'papers_marked': 0, 'errors': 0, 'batches_processed': 0}

        with database_session() as session:
            counts = fetch_and_store_inbound_citations(session, paper_ids)

        # Summary
        print('\n' + '=' * 50)
        print('INBOUND CITATIONS REPORT')
        print('=' * 50)
        print(f'Papers queried:    {total}')
        print(f'Edges inserted:    {counts["edges_inserted"]}')
        print(f'Papers marked:     {counts["papers_marked"]}')
        print(f'Batches processed: {counts["batches_processed"]}')
        print(f'Batch errors:      {counts["errors"]}')
        print('=' * 50)

        return counts

    fetch_inbound()


fetch_inbound_citations_dag()
