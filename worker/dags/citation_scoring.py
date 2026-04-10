"""
Shared citation scoring helpers used by scheduled and backfill DAGs.
"""

import json
import statistics
from bisect import bisect_left
from datetime import datetime
from typing import Dict, List, Tuple

import networkx as nx
from sqlalchemy import text
from sqlalchemy.orm import Session

from dags.citation_helpers import BATCH_SIZE
from papers.db.models import AuthorRecord, PaperAuthorRecord


def compute_pagerank(edges: List[Tuple[str, str]]) -> Dict[str, float]:
    """Build a directed graph from citation edges and compute PageRank."""
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    return nx.pagerank(graph, alpha=0.85, max_iter=100)


def compute_percentiles(scores: Dict[str, float]) -> Dict[str, float]:
    """Compute a 0-100 percentile for each score."""
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
    Compute per-author median PageRank across their linked papers.
    """
    query = text("""
        SELECT p.id, p.s2_ids->>'s2_paper_id' AS s2_paper_id
        FROM papers p
        WHERE p.s2_ids->>'s2_paper_id' IS NOT NULL
          AND p.s2_ids->>'s2_paper_id' != ''
    """)
    rows = session.execute(query).fetchall()
    paper_id_to_s2 = {row[0]: row[1] for row in rows}

    pa_rows = session.query(
        PaperAuthorRecord.paper_id,
        PaperAuthorRecord.author_id,
    ).all()
    author_rows = session.query(
        AuthorRecord.id,
        AuthorRecord.s2_author_id,
    ).all()
    author_id_to_s2 = {row[0]: row[1] for row in author_rows}

    author_paper_scores: Dict[str, List[float]] = {}
    for paper_id, author_id in pa_rows:
        s2_paper_id = paper_id_to_s2.get(paper_id)
        s2_author_id = author_id_to_s2.get(author_id)
        if not s2_paper_id or not s2_author_id:
            continue

        score = paper_scores.get(s2_paper_id)
        if score is None:
            continue

        author_paper_scores.setdefault(s2_author_id, []).append(score)

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
    Batch-update `papers.pagerank` from the current citation graph.
    """
    cited_by_query = text("""
        SELECT cited_s2_id, COUNT(*) AS cnt
        FROM paper_citations
        WHERE cited_s2_id IS NOT NULL
        GROUP BY cited_s2_id
    """)
    cited_by_rows = session.execute(cited_by_query).fetchall()
    cited_by_counts = {row[0]: row[1] for row in cited_by_rows}

    now = datetime.utcnow().isoformat() + 'Z'

    query = text("""
        SELECT id, s2_ids->>'s2_paper_id' AS s2_paper_id
        FROM papers
        WHERE s2_ids->>'s2_paper_id' IS NOT NULL
          AND s2_ids->>'s2_paper_id' != ''
    """)
    rows = session.execute(query).fetchall()

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

    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i:i + BATCH_SIZE]
        values_clause = ', '.join(
            f"({paper_id}, '{pagerank_json}'::jsonb)" for paper_id, pagerank_json in batch
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
    Batch-update `authors.pagerank` from the current citation graph.
    """
    now = datetime.utcnow().isoformat() + 'Z'
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
            f"('{author_id}', '{pagerank_json}'::jsonb)" for author_id, pagerank_json in batch
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
