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
import statistics
from bisect import bisect_left
from datetime import datetime
from typing import Dict, List, Tuple

import networkx as nx
import pendulum
from airflow.decorators import dag, task
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from papers.db.models import PaperRecord, AuthorRecord, PaperAuthorRecord
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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def fetch_papers_needing_references(session: Session) -> List[str]:
    """Compatibility wrapper: return internal nodes needing outbound reference fetch."""
    return [s2_paper_id for s2_paper_id, _ in fetch_internal_nodes_needing_outbound(session)]


def compute_pagerank(edges: List[Tuple[str, str]]) -> Dict[str, float]:
    """
    Build a networkx DiGraph from edge tuples and run PageRank.

    @param edges: List of (source_s2_id, cited_s2_id) tuples
    @returns Dict mapping s2_paper_id to PageRank score
    """
    G = nx.DiGraph()
    G.add_edges_from(edges)
    scores = nx.pagerank(G, alpha=0.85, max_iter=100)
    return scores


def compute_percentiles(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Compute percentile rank for each score. Uses bisect_left so tied scores
    get the lowest rank in the group. The top score maps to 100, the bottom
    to 0 (when total > 1).

    @param scores: Dict mapping id to score
    @returns Dict mapping id to percentile (0-100)
    """
    if not scores:
        return {}

    sorted_scores = sorted(scores.values())
    total = len(sorted_scores)

    if total == 1:
        return {key: 100.0 for key in scores}

    percentiles = {}
    for key, score in scores.items():
        rank = bisect_left(sorted_scores, score)
        percentiles[key] = rank / (total - 1) * 100

    return percentiles


def compute_author_scores(session: Session, paper_scores: Dict[str, float]) -> Dict[str, Dict]:
    """
    Compute per-author median PageRank across their papers. Uses the
    papers.id -> s2_paper_id mapping joined with paper_authors + authors.

    @param session: SQLAlchemy session
    @param paper_scores: Dict mapping s2_paper_id to PageRank score
    @returns Dict mapping s2_author_id to {"median_score": float, "scored_paper_count": int}
    """
    # Load papers.id -> s2_paper_id mapping
    query = text("""
        SELECT p.id, p.s2_ids->>'s2_paper_id' AS s2_paper_id
        FROM papers p
        WHERE p.s2_ids->>'s2_paper_id' IS NOT NULL
          AND p.s2_ids->>'s2_paper_id' != ''
    """)
    rows = session.execute(query).fetchall()
    paper_id_to_s2 = {row[0]: row[1] for row in rows}

    # Load paper_authors mappings
    pa_rows = session.query(
        PaperAuthorRecord.paper_id,
        PaperAuthorRecord.author_id,
    ).all()

    # Load author_id -> s2_author_id
    author_rows = session.query(
        AuthorRecord.id,
        AuthorRecord.s2_author_id,
    ).all()
    author_id_to_s2 = {row[0]: row[1] for row in author_rows}

    # Collect PageRank scores per author
    author_paper_scores: Dict[str, List[float]] = {}
    for paper_id, author_id in pa_rows:
        s2_paper_id = paper_id_to_s2.get(paper_id)
        s2_author_id = author_id_to_s2.get(author_id)
        if not s2_paper_id or not s2_author_id:
            continue

        score = paper_scores.get(s2_paper_id)
        if score is None:
            continue

        if s2_author_id not in author_paper_scores:
            author_paper_scores[s2_author_id] = []
        author_paper_scores[s2_author_id].append(score)

    # Compute median per author
    author_data = {}
    for s2_author_id, scores_list in author_paper_scores.items():
        author_data[s2_author_id] = {
            'median_score': statistics.median(scores_list),
            'scored_paper_count': len(scores_list),
        }

    return author_data


def write_paper_scores(
    session: Session,
    scores: Dict[str, float],
    percentiles: Dict[str, float],
) -> int:
    """
    Bulk-update papers.pagerank JSONB for all papers with an s2_paper_id in
    the scores dict. Includes cited_by_count from paper_citations (in-graph only).
    Uses a single UPDATE via VALUES list + JOIN for performance.

    @param session: SQLAlchemy session
    @param scores: Dict mapping s2_paper_id to PageRank score
    @param percentiles: Dict mapping s2_paper_id to percentile
    @returns Number of papers updated
    """
    # Compute in-graph cited_by_count for each s2_paper_id
    cited_by_query = text("""
        SELECT cited_s2_id, COUNT(*) AS cnt
        FROM paper_citations
        WHERE cited_s2_id IS NOT NULL
        GROUP BY cited_s2_id
    """)
    cited_by_rows = session.execute(cited_by_query).fetchall()
    cited_by_counts = {row[0]: row[1] for row in cited_by_rows}

    now = datetime.utcnow().isoformat() + 'Z'

    # Load papers that have s2_paper_ids in the scores dict
    query = text("""
        SELECT id, s2_ids->>'s2_paper_id' AS s2_paper_id
        FROM papers
        WHERE s2_ids->>'s2_paper_id' IS NOT NULL
          AND s2_ids->>'s2_paper_id' != ''
    """)
    rows = session.execute(query).fetchall()

    # Build batch of (paper_id, pagerank_json) pairs
    updates = []
    for row in rows:
        paper_id = row[0]
        s2_paper_id = row[1]
        if s2_paper_id not in scores:
            continue
        pagerank_data = {
            'score': scores[s2_paper_id],
            'percentile': round(percentiles.get(s2_paper_id, 0), 2),
            'cited_by_count': cited_by_counts.get(s2_paper_id, 0),
            'updated_at': now,
        }
        updates.append((paper_id, json.dumps(pagerank_data)))

    if not updates:
        return 0

    # Large single-statement updates can hit Postgres statement_timeout after
    # the graph grows. Update in batches to keep each statement bounded.
    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i:i + BATCH_SIZE]
        values_clause = ', '.join(
            f"({pid}, '{pr_json}'::jsonb)" for pid, pr_json in batch
        )
        batch_sql = f"""
            UPDATE papers AS p
            SET pagerank = v.pr
            FROM (VALUES {values_clause}) AS v(id, pr)
            WHERE p.id = v.id
        """
        session.execute(text(batch_sql))
        session.commit()

    return len(updates)


def write_author_scores(
    session: Session,
    author_data: Dict[str, Dict],
    percentiles: Dict[str, float],
) -> int:
    """
    Bulk-update authors.pagerank JSONB for all authors in the author_data dict.
    Uses a single UPDATE via VALUES list + JOIN for performance.

    @param session: SQLAlchemy session
    @param author_data: Dict mapping s2_author_id to {"median_score": float, "scored_paper_count": int}
    @param percentiles: Dict mapping s2_author_id to percentile
    @returns Number of authors updated
    """
    now = datetime.utcnow().isoformat() + 'Z'

    # Build batch of (s2_author_id, pagerank_json) pairs
    updates = []
    for s2_author_id, data in author_data.items():
        pagerank_json = {
            'median_score': data['median_score'],
            'percentile': round(percentiles.get(s2_author_id, 0), 2),
            'scored_paper_count': data['scored_paper_count'],
            'updated_at': now,
        }
        updates.append((s2_author_id, json.dumps(pagerank_json)))

    if not updates:
        return 0

    total_updated = 0
    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i:i + BATCH_SIZE]
        values_clause = ', '.join(
            f"('{aid}', '{pr_json}'::jsonb)" for aid, pr_json in batch
        )
        batch_sql = f"""
            UPDATE authors AS a
            SET pagerank = v.pr
            FROM (VALUES {values_clause}) AS v(s2_author_id, pr)
            WHERE a.s2_author_id = v.s2_author_id
        """
        result = session.execute(text(batch_sql))
        session.commit()
        total_updated += result.rowcount

    return total_updated


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
