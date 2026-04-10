"""
Deprecated wrapper for the citation inbound-selection helper.

Ongoing citation maintenance now lives in `citation_graph_dag.py`. This file is
kept only as an unscheduled compatibility wrapper for imports and manual
inspection during the transition.
"""

import sys
import pendulum
from typing import Dict, List

from airflow.decorators import dag, task
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from dags.citation_helpers import database_session, fetch_internal_nodes_needing_inbound

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def fetch_papers_needing_inbound_citations(session: Session) -> List[str]:
    """
    Compatibility wrapper around the explicit citation-node-state query.

    @param session: SQLAlchemy session
    @returns List of s2_paper_id strings needing inbound citation fetch
    """
    return fetch_internal_nodes_needing_inbound(session)


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id='fetch_inbound_citations',
    start_date=pendulum.datetime(2026, 4, 9, tz='UTC'),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'citation-graph', 'deprecated'],
    doc_md="""
    ### Fetch Inbound Citations DAG

    Deprecated compatibility DAG. The scheduled citation pipeline now lives in
    `citation_graph`.
    """,
)
def fetch_inbound_citations_dag():

    @task
    def fetch_inbound() -> Dict[str, int]:
        with database_session() as session:
            paper_ids = fetch_papers_needing_inbound_citations(session)

        print(f'Compatibility wrapper found {len(paper_ids)} internal nodes needing inbound fetch.')
        return {'internal_nodes_pending': len(paper_ids)}

    fetch_inbound()


fetch_inbound_citations_dag()
