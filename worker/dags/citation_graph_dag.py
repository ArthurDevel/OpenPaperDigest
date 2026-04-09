"""
Citation graph DAG -- fetches citation edges, computes PageRank, and writes scores.

Runs daily at 11:00 UTC (after S2 enrichment DAG at 10:00 UTC). Builds and
maintains a citation graph from Semantic Scholar reference data, then computes
PageRank scores for papers and authors.

Responsibilities:
- Fetch references for papers that have an s2_paper_id but no citation edges yet
- Store citation edges in paper_citations with INSERT ON CONFLICT DO NOTHING
- Insert sentinel rows (cited_s2_id=NULL) for papers with 0 references
- Compute PageRank over the full citation graph using networkx
- Compute percentile rankings for papers and authors
- Write scores back to papers.pagerank and authors.pagerank JSONB columns
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

from papers.db.models import PaperRecord, PaperCitationRecord, AuthorRecord, PaperAuthorRecord
from dags.citation_helpers import database_session, fetch_and_store_references, BATCH_SIZE


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def fetch_papers_needing_references(session: Session) -> List[str]:
    """
    Query papers with an s2_paper_id that don't yet appear as source_s2_id
    in paper_citations. Papers with sentinel rows (cited_s2_id=NULL) are
    correctly excluded.

    @param session: SQLAlchemy session
    @returns List of s2_paper_ids needing reference fetching
    """
    query = text("""
        SELECT DISTINCT p.s2_ids->>'s2_paper_id' AS s2_paper_id
        FROM papers p
        WHERE p.s2_ids->>'s2_paper_id' IS NOT NULL
          AND p.s2_ids->>'s2_paper_id' != ''
          AND NOT EXISTS (
              SELECT 1 FROM paper_citations pc
              WHERE pc.source_s2_id = p.s2_ids->>'s2_paper_id'
          )
    """)
    rows = session.execute(query).fetchall()
    return [row[0] for row in rows]


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

    # Batch update using VALUES list + JOIN (single round-trip)
    values_clause = ', '.join(
        f"({pid}, '{pr_json}'::jsonb)" for pid, pr_json in updates
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

    # Batch update using VALUES list + JOIN (single round-trip)
    values_clause = ', '.join(
        f"('{aid}', '{pr_json}'::jsonb)" for aid, pr_json in updates
    )
    batch_sql = f"""
        UPDATE authors AS a
        SET pagerank = v.pr
        FROM (VALUES {values_clause}) AS v(s2_author_id, pr)
        WHERE a.s2_author_id = v.s2_author_id
    """
    result = session.execute(text(batch_sql))
    session.commit()
    return result.rowcount


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

    Fetches citation edges from Semantic Scholar, computes PageRank over
    the full citation graph, and writes scores to papers and authors.
    Runs daily at 11:00 UTC after the S2 enrichment DAG.
    """,
)
def citation_graph_dag():

    @task
    def fetch_new_references() -> Dict[str, int]:
        """
        Fetch references for all papers that have an s2_paper_id but no
        citation edges yet.

        @returns Dict with edges_inserted, sentinel_rows, errors counts
        """
        with database_session() as session:
            s2_paper_ids = fetch_papers_needing_references(session)

        total = len(s2_paper_ids)
        print(f'Found {total} papers needing reference fetching')

        if total == 0:
            print('No papers need reference fetching.')
            return {'edges_inserted': 0, 'sentinel_rows': 0, 'errors': 0, 'batches_processed': 0}

        with database_session() as session:
            counts = fetch_and_store_references(session, s2_paper_ids)

        # Summary
        print('\n' + '=' * 50)
        print('REFERENCE FETCH REPORT')
        print('=' * 50)
        print(f'Papers queried:    {total}')
        print(f'Edges inserted:    {counts["edges_inserted"]}')
        print(f'Sentinel rows:     {counts["sentinel_rows"]}')
        print(f'Batches processed: {counts["batches_processed"]}')
        print(f'Batch errors:      {counts["errors"]}')
        print('=' * 50)

        return counts

    @task
    def compute_scores() -> Dict[str, int]:
        """
        Load all citation edges and compute PageRank scores + percentiles.
        Saves scores to a temp file for the write task.

        @returns Dict with node_count, edge_count
        """
        # Load all edges excluding sentinel rows
        with database_session() as session:
            query = text("""
                SELECT source_s2_id, cited_s2_id
                FROM paper_citations
                WHERE cited_s2_id IS NOT NULL
            """)
            rows = session.execute(query).fetchall()

        edges = [(row[0], row[1]) for row in rows]
        print(f'Loaded {len(edges)} citation edges')

        if len(edges) == 0:
            print('No edges found, skipping PageRank.')
            return {'node_count': 0, 'edge_count': 0}

        # Compute PageRank
        scores = compute_pagerank(edges)
        print(f'Computed PageRank for {len(scores)} nodes')

        # Compute percentiles
        percentiles = compute_percentiles(scores)

        # Save to temp file for the write_scores task
        scores_path = '/tmp/citation_graph_scores.json'
        with open(scores_path, 'w') as f:
            json.dump({'scores': scores, 'percentiles': percentiles}, f)
        print(f'Saved scores to {scores_path}')

        return {'node_count': len(scores), 'edge_count': len(edges)}

    @task
    def write_scores() -> Dict[str, int]:
        """
        Read computed PageRank scores and write them to papers and authors.

        @returns Dict with papers_updated, authors_updated counts
        """
        # Load scores from temp file
        scores_path = '/tmp/citation_graph_scores.json'
        with open(scores_path, 'r') as f:
            data = json.load(f)

        scores = data['scores']
        percentiles = data['percentiles']

        if not scores:
            print('No scores to write.')
            return {'papers_updated': 0, 'authors_updated': 0}

        # Write paper scores
        with database_session() as session:
            papers_updated = write_paper_scores(session, scores, percentiles)
        print(f'Updated {papers_updated} papers with PageRank scores')

        # Compute and write author scores
        with database_session() as session:
            author_data = compute_author_scores(session, scores)
        print(f'Computed scores for {len(author_data)} authors')

        author_score_map = {k: v['median_score'] for k, v in author_data.items()}
        author_percentiles = compute_percentiles(author_score_map)

        with database_session() as session:
            authors_updated = write_author_scores(session, author_data, author_percentiles)
        print(f'Updated {authors_updated} authors with PageRank scores')

        # Summary
        print('\n' + '=' * 50)
        print('SCORE WRITE REPORT')
        print('=' * 50)
        print(f'Papers updated:    {papers_updated}')
        print(f'Authors scored:    {len(author_data)}')
        print(f'Authors updated:   {authors_updated}')
        print('=' * 50)

        return {
            'papers_updated': papers_updated,
            'authors_updated': authors_updated,
        }

    # Task dependencies: fetch -> compute -> write
    fetch_new_references() >> compute_scores() >> write_scores()


citation_graph_dag()
