"""
Shared helpers for the citation maintenance pipeline.

The citation graph now uses an explicit `citation_node_state` table to track
which nodes have had outbound and inbound citation data fetched. The
`paper_citations` table is treated as a pure edge table; sentinel rows are no
longer written by the pipeline.
"""

import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from shared.semantic_scholar.client import fetch_paper_citations_batch, fetch_paper_references_batch


BATCH_SIZE = 500


@contextmanager
def database_session():
    """Create a database session with automatic commit/rollback handling."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _bulk_insert_edges(session: Session, edges: Sequence[Tuple[str, str, Optional[bool]]]) -> None:
    """Bulk insert citation edges using a single VALUES list with ON CONFLICT DO NOTHING."""
    if not edges:
        return

    placeholders = ', '.join(f'(:s{i}, :c{i}, :inf{i}, :now{i})' for i in range(len(edges)))
    stmt = text(
        "INSERT INTO paper_citations (source_s2_id, cited_s2_id, is_influential, created_at) "
        f"VALUES {placeholders} ON CONFLICT DO NOTHING"
    )

    params: Dict[str, object] = {}
    now = datetime.utcnow()
    for i, (source, cited, influential) in enumerate(edges):
        params[f's{i}'] = source
        params[f'c{i}'] = cited
        params[f'inf{i}'] = influential
        params[f'now{i}'] = now

    session.execute(stmt, params)


def _upsert_node_states(
    session: Session,
    nodes: Sequence[Tuple[str, Optional[int], bool, Optional[int]]],
) -> int:
    """
    Upsert citation node-state rows.

    Each tuple is `(s2_paper_id, paper_id, is_internal, hop)`.
    """
    if not nodes:
        return 0

    placeholders = ', '.join(
        f'(:s{i}, :p{i}, :internal{i}, :hop{i}, :discovered{i}, :updated{i})'
        for i in range(len(nodes))
    )
    stmt = text(
        "INSERT INTO citation_node_state "
        "(s2_paper_id, paper_id, is_internal, hop, discovered_at, updated_at) "
        f"VALUES {placeholders} "
        "ON CONFLICT (s2_paper_id) DO UPDATE SET "
        "paper_id = COALESCE(EXCLUDED.paper_id, citation_node_state.paper_id), "
        "is_internal = citation_node_state.is_internal OR EXCLUDED.is_internal, "
        "hop = CASE "
        "  WHEN citation_node_state.is_internal OR EXCLUDED.is_internal THEN 0 "
        "  WHEN citation_node_state.hop IS NULL THEN EXCLUDED.hop "
        "  WHEN EXCLUDED.hop IS NULL THEN citation_node_state.hop "
        "  ELSE LEAST(citation_node_state.hop, EXCLUDED.hop) "
        "END, "
        "updated_at = EXCLUDED.updated_at"
    )

    params: Dict[str, object] = {}
    now = datetime.utcnow()
    for i, (s2_paper_id, paper_id, is_internal, hop) in enumerate(nodes):
        params[f's{i}'] = s2_paper_id
        params[f'p{i}'] = paper_id
        params[f'internal{i}'] = is_internal
        params[f'hop{i}'] = hop
        params[f'discovered{i}'] = now
        params[f'updated{i}'] = now

    result = session.execute(stmt, params)
    rowcount = getattr(result, 'rowcount', None)
    return rowcount if isinstance(rowcount, int) and rowcount >= 0 else len(nodes)


def _mark_outbound_fetched(session: Session, s2_paper_ids: Sequence[str]) -> None:
    """Stamp outbound fetch completion on citation nodes."""
    if not s2_paper_ids:
        return

    placeholders = ', '.join(f':s{i}' for i in range(len(s2_paper_ids)))
    params = {f's{i}': s2_paper_id for i, s2_paper_id in enumerate(s2_paper_ids)}
    params['now'] = datetime.utcnow()
    session.execute(
        text(
            "UPDATE citation_node_state "
            "SET outbound_fetched_at = COALESCE(outbound_fetched_at, :now), updated_at = :now "
            f"WHERE s2_paper_id IN ({placeholders})"
        ),
        params,
    )


def _mark_inbound_fetched(session: Session, s2_paper_ids: Sequence[str]) -> None:
    """Stamp inbound fetch completion on internal citation nodes and papers."""
    if not s2_paper_ids:
        return

    placeholders = ', '.join(f':s{i}' for i in range(len(s2_paper_ids)))
    params = {f's{i}': s2_paper_id for i, s2_paper_id in enumerate(s2_paper_ids)}
    params['now'] = datetime.utcnow()

    session.execute(
        text(
            "UPDATE citation_node_state "
            "SET inbound_fetched_at = COALESCE(inbound_fetched_at, :now), updated_at = :now "
            f"WHERE s2_paper_id IN ({placeholders})"
        ),
        params,
    )
    session.execute(
        text(
            "UPDATE papers "
            "SET inbound_citations_fetched_at = COALESCE(inbound_citations_fetched_at, :now) "
            f"WHERE s2_ids->>'s2_paper_id' IN ({placeholders})"
        ),
        params,
    )


def sync_citation_node_state(session: Session) -> Dict[str, int]:
    """
    Synchronize `citation_node_state` with internal papers and already-known edges.

    This makes the new state model safe to roll out over an existing DB by
    backfilling fetch timestamps from the pre-existing `paper_citations` rows
    and `papers.inbound_citations_fetched_at`.
    """
    internal_rows = session.execute(text("""
        SELECT p.s2_ids->>'s2_paper_id' AS s2_paper_id, p.id
        FROM papers p
        WHERE p.s2_ids->>'s2_paper_id' IS NOT NULL
          AND p.s2_ids->>'s2_paper_id' != ''
    """)).fetchall()
    internal_nodes = [(row[0], row[1], True, 0) for row in internal_rows]
    internal_upserts = _upsert_node_states(session, internal_nodes)

    now = datetime.utcnow()
    session.execute(text("""
        UPDATE citation_node_state cns
        SET outbound_fetched_at = COALESCE(cns.outbound_fetched_at, :now),
            updated_at = :now
        WHERE EXISTS (
            SELECT 1
            FROM paper_citations pc
            WHERE pc.source_s2_id = cns.s2_paper_id
        )
    """), {'now': now})

    session.execute(text("""
        UPDATE citation_node_state cns
        SET inbound_fetched_at = COALESCE(cns.inbound_fetched_at, p.inbound_citations_fetched_at),
            updated_at = :now
        FROM papers p
        WHERE cns.is_internal = TRUE
          AND p.s2_ids->>'s2_paper_id' = cns.s2_paper_id
          AND p.inbound_citations_fetched_at IS NOT NULL
    """), {'now': now})

    outbound_hop1 = session.execute(text("""
        SELECT DISTINCT pc.cited_s2_id
        FROM paper_citations pc
        JOIN citation_node_state src
          ON src.s2_paper_id = pc.source_s2_id
        WHERE src.is_internal = TRUE
          AND pc.cited_s2_id IS NOT NULL
    """)).fetchall()

    inbound_hop1 = session.execute(text("""
        SELECT DISTINCT pc.source_s2_id
        FROM paper_citations pc
        JOIN citation_node_state dst
          ON dst.s2_paper_id = pc.cited_s2_id
        WHERE dst.is_internal = TRUE
    """)).fetchall()

    outbound_hop2 = session.execute(text("""
        SELECT DISTINCT pc.cited_s2_id
        FROM paper_citations pc
        JOIN citation_node_state src
          ON src.s2_paper_id = pc.source_s2_id
        WHERE src.is_internal = FALSE
          AND src.hop = 1
          AND pc.cited_s2_id IS NOT NULL
    """)).fetchall()

    external_nodes = (
        [(row[0], None, False, 1) for row in outbound_hop1] +
        [(row[0], None, False, 1) for row in inbound_hop1] +
        [(row[0], None, False, 2) for row in outbound_hop2]
    )
    external_upserts = _upsert_node_states(session, external_nodes)

    return {
        'internal_upserts': internal_upserts,
        'external_upserts': external_upserts,
    }


def fetch_internal_nodes_needing_outbound(session: Session) -> List[Tuple[str, int]]:
    """Return internal nodes whose outbound references have not yet been fetched."""
    rows = session.execute(text("""
        SELECT s2_paper_id, hop
        FROM citation_node_state
        WHERE is_internal = TRUE
          AND outbound_fetched_at IS NULL
        ORDER BY updated_at ASC NULLS FIRST, s2_paper_id
    """)).fetchall()
    return [(row[0], row[1] or 0) for row in rows]


def fetch_internal_nodes_needing_inbound(session: Session) -> List[str]:
    """Return internal nodes whose inbound citations have not yet been fetched."""
    rows = session.execute(text("""
        SELECT s2_paper_id
        FROM citation_node_state
        WHERE is_internal = TRUE
          AND inbound_fetched_at IS NULL
        ORDER BY updated_at ASC NULLS FIRST, s2_paper_id
    """)).fetchall()
    return [row[0] for row in rows]


def fetch_external_nodes_needing_outbound(session: Session) -> List[Tuple[str, int]]:
    """Return one-hop external nodes whose outbound references have not yet been fetched."""
    rows = session.execute(text("""
        SELECT s2_paper_id, hop
        FROM citation_node_state
        WHERE is_internal = FALSE
          AND hop = 1
          AND outbound_fetched_at IS NULL
        ORDER BY updated_at ASC NULLS FIRST, s2_paper_id
    """)).fetchall()
    return [(row[0], row[1] or 1) for row in rows]


def fetch_and_store_references(session: Session, nodes: List[Tuple[str, int]]) -> Dict[str, int]:
    """
    Fetch outbound references for the supplied nodes and update node-state rows.

    `nodes` is a list of `(s2_paper_id, hop)` pairs.
    """
    total_edges = 0
    total_errors = 0
    batches_processed = 0
    nodes_marked = 0
    nodes_discovered = 0

    for i in range(0, len(nodes), BATCH_SIZE):
        batch = nodes[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        batch_ids = [node_id for node_id, _ in batch]
        hop_by_id = {node_id: hop for node_id, hop in batch}
        print(f'  Batch {batch_num}: fetching references for {len(batch)} citation nodes...')

        try:
            references = fetch_paper_references_batch(batch_ids)
            edges = [(ref.source_s2_id, ref.cited_s2_id, ref.is_influential) for ref in references]
            _bulk_insert_edges(session, edges)
            total_edges += len(edges)

            discovered_nodes = {}
            for ref in references:
                source_hop = hop_by_id.get(ref.source_s2_id, 0)
                next_hop = min(source_hop + 1, 2)
                current_hop = discovered_nodes.get(ref.cited_s2_id)
                if current_hop is None or next_hop < current_hop:
                    discovered_nodes[ref.cited_s2_id] = next_hop

            if discovered_nodes:
                nodes_discovered += _upsert_node_states(
                    session,
                    [(s2_id, None, False, hop) for s2_id, hop in discovered_nodes.items()],
                )

            _mark_outbound_fetched(session, batch_ids)
            nodes_marked += len(batch_ids)
            session.commit()
            batches_processed += 1
            print(f'    Edges: {len(edges)}, Nodes marked outbound-fetched: {len(batch_ids)}')

        except Exception as e:
            print(f'    ERROR in batch {batch_num}: {e}')
            session.rollback()
            total_errors += 1

    return {
        'edges_inserted': total_edges,
        'errors': total_errors,
        'batches_processed': batches_processed,
        'nodes_marked': nodes_marked,
        'nodes_discovered': nodes_discovered,
    }


def fetch_and_store_inbound_citations(session: Session, s2_paper_ids: List[str]) -> Dict[str, int]:
    """
    Fetch inbound citations for internal nodes and update node-state rows.
    """
    total_edges = 0
    total_papers_marked = 0
    total_errors = 0
    batches_processed = 0
    nodes_discovered = 0

    for i in range(0, len(s2_paper_ids), BATCH_SIZE):
        batch = s2_paper_ids[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        print(f'  Batch {batch_num}: fetching inbound citations for {len(batch)} citation nodes...')

        try:
            citations = fetch_paper_citations_batch(batch)
            edges = [(cit.citing_s2_id, cit.cited_s2_id, cit.is_influential) for cit in citations]
            _bulk_insert_edges(session, edges)
            total_edges += len(edges)

            discovered_sources = {cit.citing_s2_id for cit in citations}
            if discovered_sources:
                nodes_discovered += _upsert_node_states(
                    session,
                    [(s2_id, None, False, 1) for s2_id in discovered_sources],
                )

            _mark_inbound_fetched(session, batch)
            total_papers_marked += len(batch)
            session.commit()
            batches_processed += 1
            print(f'    Edges: {len(edges)}, Nodes marked inbound-fetched: {len(batch)}')

        except Exception as e:
            print(f'    ERROR in batch {batch_num}: {e}')
            session.rollback()
            total_errors += 1

    return {
        'edges_inserted': total_edges,
        'papers_marked': total_papers_marked,
        'errors': total_errors,
        'batches_processed': batches_processed,
        'nodes_discovered': nodes_discovered,
    }
