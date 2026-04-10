"""
Citation graph DAG -- the single scheduled owner of citation maintenance.

Runs daily at 11:00 UTC (after S2 enrichment DAG at 10:00 UTC). The DAG:

1. syncs explicit citation node state for internal and already-known external nodes
2. fetches outbound references for internal papers
3. fetches inbound citations for internal papers
4. expands one-hop external nodes
5. recomputes and writes PageRank scores
"""

import json
import sys
from typing import Dict, List, Tuple

import pendulum
from airflow.decorators import dag, task
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from dags.citation_helpers import (
    BATCH_SIZE,
    database_session,
    fetch_and_store_inbound_citations,
    fetch_and_store_references,
    fetch_external_nodes_needing_outbound,
    fetch_internal_nodes_needing_inbound,
    fetch_internal_nodes_needing_outbound,
    sync_citation_node_state,
)
from dags.citation_scoring import (
    compute_author_scores,
    compute_pagerank,
    compute_percentiles,
    write_author_scores,
    write_paper_scores,
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def fetch_papers_needing_references(session: Session) -> List[str]:
    """Compatibility wrapper: return internal nodes needing outbound reference fetch."""
    return [s2_paper_id for s2_paper_id, _ in fetch_internal_nodes_needing_outbound(session)]


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id='citation_graph',
    start_date=pendulum.datetime(2026, 4, 2, tz='UTC'),
    schedule='0 11 * * *',  # Daily at 11:00 UTC
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'citation-graph', 'pagerank', 'daily'],
    doc_md="""
    ### Citation Graph DAG

    Single scheduled owner of citation maintenance.

    The DAG syncs explicit citation node state, fetches internal outbound and
    inbound edges, expands one-hop external nodes, and recomputes PageRank.
    """,
)
def citation_graph_dag():

    @task
    def sync_node_state() -> Dict[str, int]:
        """
        Backfill/refresh explicit citation node-state rows from internal papers
        and any already-known citation edges.
        """
        with database_session() as session:
            counts = sync_citation_node_state(session)

        print('\n' + '=' * 50)
        print('CITATION NODE STATE REPORT')
        print('=' * 50)
        print(f'Internal upserts:  {counts["internal_upserts"]}')
        print(f'External upserts:  {counts["external_upserts"]}')
        print('=' * 50)
        return counts

    @task
    def fetch_internal_outbound() -> Dict[str, int]:
        """
        Fetch outbound references for internal papers that have not yet been fetched.
        """
        with database_session() as session:
            nodes = fetch_internal_nodes_needing_outbound(session)

        total = len(nodes)
        print(f'Found {total} internal nodes needing outbound references')

        if total == 0:
            print('No internal nodes need outbound fetch.')
            return {'edges_inserted': 0, 'errors': 0, 'batches_processed': 0, 'nodes_marked': 0, 'nodes_discovered': 0}

        with database_session() as session:
            counts = fetch_and_store_references(session, nodes)

        print('\n' + '=' * 50)
        print('INTERNAL OUTBOUND REPORT')
        print('=' * 50)
        print(f'Nodes queried:     {total}')
        print(f'Edges inserted:    {counts["edges_inserted"]}')
        print(f'Nodes marked:      {counts["nodes_marked"]}')
        print(f'Nodes discovered:  {counts["nodes_discovered"]}')
        print(f'Batches processed: {counts["batches_processed"]}')
        print(f'Batch errors:      {counts["errors"]}')
        print('=' * 50)
        return counts

    @task
    def fetch_internal_inbound() -> Dict[str, int]:
        """
        Fetch inbound citations for internal papers that have not yet been fetched.
        """
        with database_session() as session:
            s2_paper_ids = fetch_internal_nodes_needing_inbound(session)

        total = len(s2_paper_ids)
        print(f'Found {total} internal nodes needing inbound citations')

        if total == 0:
            print('No internal nodes need inbound fetch.')
            return {'edges_inserted': 0, 'papers_marked': 0, 'errors': 0, 'batches_processed': 0, 'nodes_discovered': 0}

        with database_session() as session:
            counts = fetch_and_store_inbound_citations(session, s2_paper_ids)

        print('\n' + '=' * 50)
        print('INTERNAL INBOUND REPORT')
        print('=' * 50)
        print(f'Nodes queried:     {total}')
        print(f'Edges inserted:    {counts["edges_inserted"]}')
        print(f'Nodes marked:      {counts["papers_marked"]}')
        print(f'Nodes discovered:  {counts["nodes_discovered"]}')
        print(f'Batches processed: {counts["batches_processed"]}')
        print(f'Batch errors:      {counts["errors"]}')
        print('=' * 50)
        return counts

    @task
    def expand_external_outbound() -> Dict[str, int]:
        """
        Fetch outbound references for one-hop external nodes.
        """
        with database_session() as session:
            nodes = fetch_external_nodes_needing_outbound(session)

        total = len(nodes)
        print(f'Found {total} one-hop external nodes needing outbound references')

        if total == 0:
            print('No one-hop external nodes need expansion.')
            return {'edges_inserted': 0, 'errors': 0, 'batches_processed': 0, 'nodes_marked': 0, 'nodes_discovered': 0}

        with database_session() as session:
            counts = fetch_and_store_references(session, nodes)

        print('\n' + '=' * 50)
        print('EXTERNAL EXPANSION REPORT')
        print('=' * 50)
        print(f'Nodes queried:     {total}')
        print(f'Edges inserted:    {counts["edges_inserted"]}')
        print(f'Nodes marked:      {counts["nodes_marked"]}')
        print(f'Nodes discovered:  {counts["nodes_discovered"]}')
        print(f'Batches processed: {counts["batches_processed"]}')
        print(f'Batch errors:      {counts["errors"]}')
        print('=' * 50)
        return counts

    @task
    def compute_and_write_scores() -> Dict[str, int]:
        """
        Compute PageRank from the edge table and write paper/author scores.
        """
        with database_session() as session:
            edge_rows = session.execute(text("""
                SELECT source_s2_id, cited_s2_id
                FROM paper_citations
                WHERE cited_s2_id IS NOT NULL
            """)).fetchall()

        edges = [(row[0], row[1]) for row in edge_rows]
        print(f'Loaded {len(edges)} citation edges')

        if not edges:
            print('No edges found, skipping PageRank.')
            return {'node_count': 0, 'edge_count': 0, 'papers_updated': 0, 'authors_updated': 0}

        scores = compute_pagerank(edges)
        percentiles = compute_percentiles(scores)
        with database_session() as session:
            papers_updated = write_paper_scores(session, scores, percentiles)
            author_data = compute_author_scores(session, scores)
        author_score_map = {k: v['median_score'] for k, v in author_data.items()}
        author_percentiles = compute_percentiles(author_score_map)
        with database_session() as session:
            authors_updated = write_author_scores(session, author_data, author_percentiles)

        print('\n' + '=' * 50)
        print('CITATION SCORE REPORT')
        print('=' * 50)
        print(f'Graph nodes:        {len(scores)}')
        print(f'Graph edges:        {len(edges)}')
        print(f'Papers updated:    {papers_updated}')
        print(f'Authors scored:    {len(author_data)}')
        print(f'Authors updated:   {authors_updated}')
        print('=' * 50)

        return {
            'node_count': len(scores),
            'edge_count': len(edges),
            'papers_updated': papers_updated,
            'authors_updated': authors_updated,
        }

    sync_node_state() >> fetch_internal_outbound() >> fetch_internal_inbound() >> expand_external_outbound() >> compute_and_write_scores()


citation_graph_dag()
