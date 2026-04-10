"""
Deprecated wrapper for the citation expansion selection helper.

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

from dags.citation_helpers import database_session, fetch_external_nodes_needing_outbound

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def fetch_external_nodes_needing_references(session: Session) -> List[str]:
    """
    Compatibility wrapper around the explicit citation-node-state query.

    @param session: SQLAlchemy session
    @returns List of s2_paper_ids for external nodes needing reference fetching
    """
    return [s2_paper_id for s2_paper_id, _ in fetch_external_nodes_needing_outbound(session)]


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id='expand_external_references',
    start_date=pendulum.datetime(2026, 4, 2, tz='UTC'),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'citation-graph', 'deprecated'],
    doc_md="""
    ### Expand External References DAG

    Deprecated compatibility DAG. The scheduled citation pipeline now lives in
    `citation_graph`.
    """,
)
def expand_external_references_dag():

    @task
    def expand_external() -> Dict[str, int]:
        with database_session() as session:
            external_ids = fetch_external_nodes_needing_references(session)

        print(f'Compatibility wrapper found {len(external_ids)} external nodes needing outbound fetch.')
        return {'external_nodes_pending': len(external_ids)}

    expand_external()


expand_external_references_dag()
