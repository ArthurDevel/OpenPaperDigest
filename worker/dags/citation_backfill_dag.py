"""
Manual backfill for the citation domain.

This DAG repairs citation-owned state only:
- citation node-state rows
- missing outbound/inbound fetch progress
- one-hop external expansion
- paper/author PageRank
"""

import sys
from typing import Dict

import pendulum
from airflow.decorators import dag, task
from sqlalchemy import text

sys.path.insert(0, '/opt/airflow')

from dags.citation_helpers import (
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


@dag(
    dag_id='citation_backfill',
    start_date=pendulum.datetime(2025, 1, 1, tz='UTC'),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'backfill', 'citation'],
    doc_md="""
    ### Citation Backfill

    Manual backfill aligned to the citation ownership domain. It walks the full
    backlog of citation work until there are no remaining internal or one-hop
    external nodes missing fetch progress, then rewrites PageRank.
    """,
)
def citation_backfill_dag():

    @task
    def sync_node_state() -> Dict[str, int]:
        with database_session() as session:
            return sync_citation_node_state(session)

    @task
    def backfill_internal_outbound() -> Dict[str, int]:
        total_edges = 0
        total_errors = 0
        total_batches = 0
        total_marked = 0
        total_discovered = 0

        while True:
            with database_session() as session:
                nodes = fetch_internal_nodes_needing_outbound(session)
            if not nodes:
                break

            with database_session() as session:
                counts = fetch_and_store_references(session, nodes)
            total_edges += counts['edges_inserted']
            total_errors += counts['errors']
            total_batches += counts['batches_processed']
            total_marked += counts['nodes_marked']
            total_discovered += counts['nodes_discovered']

        return {
            'edges_inserted': total_edges,
            'errors': total_errors,
            'batches_processed': total_batches,
            'nodes_marked': total_marked,
            'nodes_discovered': total_discovered,
        }

    @task
    def backfill_internal_inbound() -> Dict[str, int]:
        total_edges = 0
        total_errors = 0
        total_batches = 0
        total_marked = 0
        total_discovered = 0

        while True:
            with database_session() as session:
                s2_paper_ids = fetch_internal_nodes_needing_inbound(session)
            if not s2_paper_ids:
                break

            with database_session() as session:
                counts = fetch_and_store_inbound_citations(session, s2_paper_ids)
            total_edges += counts['edges_inserted']
            total_errors += counts['errors']
            total_batches += counts['batches_processed']
            total_marked += counts['papers_marked']
            total_discovered += counts['nodes_discovered']

        return {
            'edges_inserted': total_edges,
            'errors': total_errors,
            'batches_processed': total_batches,
            'papers_marked': total_marked,
            'nodes_discovered': total_discovered,
        }

    @task
    def backfill_external_outbound() -> Dict[str, int]:
        total_edges = 0
        total_errors = 0
        total_batches = 0
        total_marked = 0
        total_discovered = 0

        while True:
            with database_session() as session:
                nodes = fetch_external_nodes_needing_outbound(session)
            if not nodes:
                break

            with database_session() as session:
                counts = fetch_and_store_references(session, nodes)
            total_edges += counts['edges_inserted']
            total_errors += counts['errors']
            total_batches += counts['batches_processed']
            total_marked += counts['nodes_marked']
            total_discovered += counts['nodes_discovered']

        return {
            'edges_inserted': total_edges,
            'errors': total_errors,
            'batches_processed': total_batches,
            'nodes_marked': total_marked,
            'nodes_discovered': total_discovered,
        }

    @task
    def compute_and_write_scores() -> Dict[str, int]:
        with database_session() as session:
            edge_rows = session.execute(text("""
                SELECT source_s2_id, cited_s2_id
                FROM paper_citations
                WHERE cited_s2_id IS NOT NULL
            """)).fetchall()

        edges = [(row[0], row[1]) for row in edge_rows]
        if not edges:
            return {'node_count': 0, 'edge_count': 0, 'papers_updated': 0, 'authors_updated': 0}

        scores = compute_pagerank(edges)
        percentiles = compute_percentiles(scores)

        with database_session() as session:
            papers_updated = write_paper_scores(session, scores, percentiles)
            author_data = compute_author_scores(session, scores)

        author_percentiles = compute_percentiles(
            {author_id: data['median_score'] for author_id, data in author_data.items()}
        )
        with database_session() as session:
            authors_updated = write_author_scores(session, author_data, author_percentiles)

        return {
            'node_count': len(scores),
            'edge_count': len(edges),
            'papers_updated': papers_updated,
            'authors_updated': authors_updated,
        }

    sync_node_state() >> backfill_internal_outbound() >> backfill_internal_inbound() >> backfill_external_outbound() >> compute_and_write_scores()


citation_backfill_dag()
