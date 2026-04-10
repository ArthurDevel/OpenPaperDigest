"""Focused tests for the citation maintenance pipeline."""

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from shared.semantic_scholar.models import S2PaperCitation, S2PaperReference
from shared.semantic_scholar.client import fetch_paper_citations_batch, fetch_paper_references_batch


sys.modules.setdefault('airflow', MagicMock())
sys.modules.setdefault('airflow.decorators', MagicMock())

DAGS_DIR = WORKER_ROOT / 'dags'
if str(DAGS_DIR) not in sys.path:
    sys.path.insert(0, str(DAGS_DIR))

from citation_graph_dag import (
    compute_author_scores,
    compute_pagerank,
    compute_percentiles,
    fetch_papers_needing_references,
    write_author_scores,
    write_paper_scores,
)
from citation_helpers import (
    BATCH_SIZE,
    fetch_and_store_inbound_citations,
    fetch_and_store_references,
)
from deprecated_expand_external_references_dag import fetch_external_nodes_needing_references
from enrich_s2_paper_data_dag import refresh_paper_signals
from deprecated_fetch_inbound_citations_dag import fetch_papers_needing_inbound_citations


MOCK_REFERENCES_RESPONSE = [
    {'references': [{'paperId': 'ref1', 'isInfluential': True}, {'paperId': 'ref2', 'isInfluential': False}]},
    None,
    {'references': [{'paperId': 'ref3', 'isInfluential': None}, {'paperId': None, 'isInfluential': False}]},
]

MOCK_CITATIONS_RESPONSE = [
    {'citations': [{'paperId': 'citer1'}, {'paperId': 'citer2'}]},
    None,
    {'citations': [{'paperId': 'citer3'}, {'paperId': None}]},
]


@patch('shared.semantic_scholar.client._request_with_retry')
def test_fetch_paper_references_batch(mock_request):
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_REFERENCES_RESPONSE
    mock_request.return_value = mock_response

    results = fetch_paper_references_batch(['paper_a', 'paper_b', 'paper_c'])

    assert len(results) == 3
    assert results[0].source_s2_id == 'paper_a'
    assert results[0].cited_s2_id == 'ref1'
    assert results[1].cited_s2_id == 'ref2'
    assert results[2].source_s2_id == 'paper_c'
    assert results[2].cited_s2_id == 'ref3'


@patch('shared.semantic_scholar.client._request_with_retry')
def test_fetch_paper_citations_batch(mock_request):
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_CITATIONS_RESPONSE
    mock_request.return_value = mock_response

    results = fetch_paper_citations_batch(['our_a', 'our_b', 'our_c'])

    assert len(results) == 3
    assert results[0].cited_s2_id == 'our_a'
    assert results[0].citing_s2_id == 'citer1'
    assert results[2].cited_s2_id == 'our_c'
    assert results[2].citing_s2_id == 'citer3'


def test_compute_pagerank_known_graph():
    scores = compute_pagerank([('A', 'B'), ('B', 'C'), ('A', 'C')])
    assert scores['C'] > scores['B'] > scores['A']


def test_compute_percentiles_basic():
    percentiles = compute_percentiles({'a': 1.0, 'b': 2.0, 'c': 3.0, 'd': 4.0})
    assert percentiles['a'] == pytest.approx(0.0)
    assert percentiles['d'] == pytest.approx(100.0)


def test_compute_author_scores():
    session = MagicMock()
    paper_rows = MagicMock()
    paper_rows.fetchall.return_value = [(1, 'sp1'), (2, 'sp2'), (3, 'sp3')]
    session.execute.return_value = paper_rows
    session.query.return_value.all = MagicMock(side_effect=[
        [(1, 100), (3, 100), (2, 200)],
        [(100, 'sa1'), (200, 'sa2')],
    ])

    result = compute_author_scores(session, {'sp1': 0.1, 'sp2': 0.3, 'sp3': 0.5})
    assert result['sa1']['median_score'] == 0.3
    assert result['sa1']['scored_paper_count'] == 2
    assert result['sa2']['median_score'] == 0.3


@patch('citation_helpers.fetch_paper_references_batch')
def test_fetch_and_store_references_marks_nodes_without_sentinels(mock_fetch):
    mock_fetch.return_value = []

    session = MagicMock()
    counts = fetch_and_store_references(session, [('paper_x', 0)])

    assert counts['edges_inserted'] == 0
    assert counts['nodes_marked'] == 1
    assert counts['nodes_discovered'] == 0

    executed_sql = [str(call.args[0]) for call in session.execute.call_args_list]
    assert any('UPDATE citation_node_state' in sql for sql in executed_sql)
    assert not any('VALUES (:source, NULL' in sql for sql in executed_sql)


@patch('citation_helpers.fetch_paper_references_batch')
def test_fetch_and_store_references_discovers_new_nodes(mock_fetch):
    mock_fetch.return_value = [
        S2PaperReference(source_s2_id='paper_a', cited_s2_id='ext1', is_influential=True),
        S2PaperReference(source_s2_id='paper_a', cited_s2_id='ext2', is_influential=False),
    ]

    session = MagicMock()
    counts = fetch_and_store_references(session, [('paper_a', 0)])

    assert counts['edges_inserted'] == 2
    assert counts['nodes_marked'] == 1
    assert counts['nodes_discovered'] == 2


def test_fetch_papers_needing_references_uses_node_state():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [('paper_new', 0)]
    session.execute.return_value = mock_result

    result = fetch_papers_needing_references(session)

    assert result == ['paper_new']
    query_sql = str(session.execute.call_args.args[0])
    assert 'citation_node_state' in query_sql
    assert 'outbound_fetched_at IS NULL' in query_sql


def test_fetch_external_nodes_needing_references_uses_node_state():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [('ext1', 1), ('ext2', 1)]
    session.execute.return_value = mock_result

    result = fetch_external_nodes_needing_references(session)

    assert result == ['ext1', 'ext2']
    query_sql = str(session.execute.call_args.args[0])
    assert 'citation_node_state' in query_sql
    assert 'hop = 1' in query_sql


@patch('citation_helpers.fetch_paper_citations_batch')
def test_fetch_and_store_inbound_citations_marks_internal_nodes(mock_fetch):
    mock_fetch.return_value = [
        S2PaperCitation(cited_s2_id='our_paper', citing_s2_id='citerX', is_influential=None),
        S2PaperCitation(cited_s2_id='our_paper', citing_s2_id='citerY', is_influential=None),
    ]

    session = MagicMock()
    counts = fetch_and_store_inbound_citations(session, ['our_paper'])

    assert counts['edges_inserted'] == 2
    assert counts['papers_marked'] == 1
    assert counts['nodes_discovered'] == 2

    executed_sql = [str(call.args[0]) for call in session.execute.call_args_list]
    assert any('INSERT INTO paper_citations' in sql for sql in executed_sql)
    assert any('UPDATE citation_node_state' in sql for sql in executed_sql)
    assert any('UPDATE papers' in sql for sql in executed_sql)


def test_fetch_papers_needing_inbound_citations_uses_node_state():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [('paper_new1',), ('paper_new2',)]
    session.execute.return_value = mock_result

    result = fetch_papers_needing_inbound_citations(session)

    assert result == ['paper_new1', 'paper_new2']
    query_sql = str(session.execute.call_args.args[0])
    assert 'citation_node_state' in query_sql
    assert 'inbound_fetched_at IS NULL' in query_sql


def test_write_paper_scores_batches_updates():
    session = MagicMock()
    cited_by_result = MagicMock()
    cited_by_result.fetchall.return_value = [('s2_0', 3), ('s2_500', 1)]
    papers_result = MagicMock()
    papers_result.fetchall.return_value = [(i, f's2_{i}') for i in range(BATCH_SIZE + 1)]
    session.execute.side_effect = [cited_by_result, papers_result, MagicMock(), MagicMock()]

    scores = {f's2_{i}': float(i + 1) for i in range(BATCH_SIZE + 1)}
    percentiles = {f's2_{i}': float(i % 100) for i in range(BATCH_SIZE + 1)}

    updated = write_paper_scores(session, scores, percentiles)

    assert updated == BATCH_SIZE + 1
    assert session.commit.call_count == 2


def test_write_author_scores_batches_updates():
    session = MagicMock()
    first_result = MagicMock()
    first_result.rowcount = BATCH_SIZE
    second_result = MagicMock()
    second_result.rowcount = 1
    session.execute.side_effect = [first_result, second_result]

    author_data = {
        f'auth_{i}': {'median_score': float(i + 1), 'scored_paper_count': 1}
        for i in range(BATCH_SIZE + 1)
    }
    percentiles = {f'auth_{i}': float(i % 100) for i in range(BATCH_SIZE + 1)}

    updated = write_author_scores(session, author_data, percentiles)

    assert updated == BATCH_SIZE + 1
    assert session.commit.call_count == 2


def test_refresh_paper_signals_batches_updates(monkeypatch):
    total_papers = BATCH_SIZE + 1
    paper_ids = list(range(1, total_papers + 1))
    sessions = []

    def make_session(batch_ids):
        session = MagicMock()
        rows = [SimpleNamespace(paper_id=paper_id, max_h_index=paper_id + 10) for paper_id in batch_ids]
        papers = [
            SimpleNamespace(
                id=paper_id,
                signals={'existing': True},
                signals_refreshed_at=None,
                s2_enrichment_error=None,
            )
            for paper_id in batch_ids
        ]

        aggregate_query = MagicMock()
        aggregate_query.join.return_value.filter.return_value.group_by.return_value.all.return_value = rows

        paper_query = MagicMock()
        paper_query.filter.return_value.all.return_value = papers

        session.query.side_effect = [aggregate_query, paper_query]
        session._papers = papers
        sessions.append(session)
        return session

    batches = [paper_ids[i:i + BATCH_SIZE] for i in range(0, len(paper_ids), BATCH_SIZE)]
    session_iter = iter(make_session(batch_ids) for batch_ids in batches)

    @contextmanager
    def fake_database_session():
        yield next(session_iter)

    monkeypatch.setattr('enrich_s2_paper_data_dag.database_session', fake_database_session)

    counts = refresh_paper_signals(paper_ids)

    assert counts == {'updated': total_papers, 'failed': 0}
    assert len(sessions) == 2
    assert all(paper.signals['max_author_h_index'] == paper.id + 10 for session in sessions for paper in session._papers)
    assert all(paper.signals_refreshed_at is not None for session in sessions for paper in session._papers)
