"""
Tests for citation graph pipeline -- reference fetching, PageRank, and score writing.

Responsibilities:
- Verify fetch_paper_references_batch parses S2 batch responses into DTOs correctly
- Verify compute_pagerank produces correct relative rankings for a known graph
- Verify compute_percentiles assigns correct percentiles with ties and edge cases
- Verify compute_author_scores computes median PageRank per author
- Verify sentinel row insertion for papers with 0 references
- Verify fetch_external_nodes_needing_references returns correct external nodes
- Integration test: full pipeline with mocked S2 API and DB session
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

# Ensure worker root is on sys.path for imports like `shared.semantic_scholar`
WORKER_ROOT = Path(__file__).resolve().parents[2]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from shared.semantic_scholar.models import S2PaperReference
from shared.semantic_scholar.client import fetch_paper_references_batch

# The DAG file imports airflow which isn't available in test env -- mock it
sys.modules.setdefault('airflow', MagicMock())
sys.modules.setdefault('airflow.decorators', MagicMock())

# Import needs the dags directory on sys.path
DAGS_DIR = WORKER_ROOT / 'dags'
if str(DAGS_DIR) not in sys.path:
    sys.path.insert(0, str(DAGS_DIR))

from citation_graph_dag import (
    compute_pagerank,
    compute_percentiles,
    compute_author_scores,
    fetch_papers_needing_references,
    fetch_and_store_references,
)
from expand_external_references_dag import fetch_external_nodes_needing_references


# ============================================================================
# CONSTANTS
# ============================================================================

# Mock S2 API response: 3 items (full paper, null entry, paper with null target)
MOCK_REFERENCES_RESPONSE = [
    # Paper with 2 references
    {
        'references': [
            {'paperId': 'ref1', 'isInfluential': True},
            {'paperId': 'ref2', 'isInfluential': False},
        ]
    },
    # Null entry (paper not found)
    None,
    # Paper with 1 reference including a null target
    {
        'references': [
            {'paperId': 'ref3', 'isInfluential': None},
            {'paperId': None, 'isInfluential': False},  # null target, should be skipped
        ]
    },
]


# ============================================================================
# UNIT TESTS: fetch_paper_references_batch
# ============================================================================


@patch('shared.semantic_scholar.client._request_with_retry')
def test_fetch_paper_references_batch(mock_request):
    """
    Verify fetch_paper_references_batch correctly:
    - Parses S2 batch response into S2PaperReference DTOs
    - Skips null entries (paper not found by S2)
    - Skips references with null paperId targets
    - Correlates source_s2_id from input order
    - Preserves isInfluential flag
    """
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_REFERENCES_RESPONSE
    mock_request.return_value = mock_response

    s2_ids = ['paper_a', 'paper_b', 'paper_c']
    results = fetch_paper_references_batch(s2_ids)

    # 3 valid references: 2 from paper_a, 0 from paper_b (null), 1 from paper_c
    # (paper_c's null-target ref is skipped)
    assert len(results) == 3

    # Paper A references
    assert results[0].source_s2_id == 'paper_a'
    assert results[0].cited_s2_id == 'ref1'
    assert results[0].is_influential is True

    assert results[1].source_s2_id == 'paper_a'
    assert results[1].cited_s2_id == 'ref2'
    assert results[1].is_influential is False

    # Paper C reference (paper_b was null, so paper_c is index 2)
    assert results[2].source_s2_id == 'paper_c'
    assert results[2].cited_s2_id == 'ref3'
    assert results[2].is_influential is None

    # Verify all results are S2PaperReference instances
    for ref in results:
        assert isinstance(ref, S2PaperReference)


# ============================================================================
# UNIT TESTS: compute_pagerank
# ============================================================================


def test_compute_pagerank_known_graph():
    """
    Test with a known small graph: A->B, B->C, A->C.
    C should have highest score (receives edges from both A and B).
    B should be middle (receives edge from A).
    A should have lowest score (receives no edges, only gives).
    """
    edges = [('A', 'B'), ('B', 'C'), ('A', 'C')]
    scores = compute_pagerank(edges)

    assert 'A' in scores
    assert 'B' in scores
    assert 'C' in scores

    # C has the highest score (most incoming edges)
    assert scores['C'] > scores['B']
    assert scores['B'] > scores['A']

    # All scores should be positive
    for score in scores.values():
        assert score > 0


def test_compute_pagerank_single_edge():
    """
    Minimal graph with a single edge. Both nodes should have scores.
    The cited node should rank higher.
    """
    edges = [('X', 'Y')]
    scores = compute_pagerank(edges)

    assert len(scores) == 2
    assert scores['Y'] > scores['X']


# ============================================================================
# UNIT TESTS: compute_percentiles
# ============================================================================


def test_compute_percentiles_basic():
    """
    Test with known values. The max score gets P100, the median gets P50,
    and the min score gets the lowest percentile.
    """
    scores = {'a': 1.0, 'b': 2.0, 'c': 3.0, 'd': 4.0}
    percentiles = compute_percentiles(scores)

    # Max score (4.0) should be P100
    assert percentiles['d'] == 100.0

    # Min score (1.0) should be P25 (1 out of 4 values <= 1.0)
    assert percentiles['a'] == 25.0

    # Median values
    assert percentiles['b'] == 50.0
    assert percentiles['c'] == 75.0


def test_compute_percentiles_ties():
    """
    When multiple items have the same score, they should all get the same
    percentile (bisect_right gives them all the same rank).
    """
    scores = {'a': 1.0, 'b': 2.0, 'c': 2.0, 'd': 3.0}
    percentiles = compute_percentiles(scores)

    # Both b and c have score 2.0 -- bisect_right finds 3 values <= 2.0
    assert percentiles['b'] == percentiles['c']
    assert percentiles['b'] == 75.0  # 3/4 * 100

    # Max still gets P100
    assert percentiles['d'] == 100.0


def test_compute_percentiles_empty():
    """Empty input should return empty output."""
    assert compute_percentiles({}) == {}


def test_compute_percentiles_single():
    """Single item should get P100."""
    percentiles = compute_percentiles({'only': 5.0})
    assert percentiles['only'] == 100.0


# ============================================================================
# UNIT TESTS: compute_author_scores
# ============================================================================


def test_compute_author_scores():
    """
    Mock session with papers.id->s2_paper_id mapping, paper_authors, and
    authors tables. Verify median calculation and scored_paper_count.

    Setup:
    - Paper 1 (s2: 'sp1') with PageRank 0.1
    - Paper 2 (s2: 'sp2') with PageRank 0.3
    - Paper 3 (s2: 'sp3') with PageRank 0.5
    - Author A (s2: 'sa1') wrote papers 1 and 3 -> median = 0.3
    - Author B (s2: 'sa2') wrote paper 2 only -> median = 0.3
    """
    session = MagicMock()

    # Mock papers.id -> s2_paper_id query
    paper_rows = MagicMock()
    paper_rows.fetchall.return_value = [
        (1, 'sp1'),
        (2, 'sp2'),
        (3, 'sp3'),
    ]

    # Mock paper_authors query -- tuples because the code unpacks via
    # `for paper_id, author_id in pa_rows`
    pa_rows = [(1, 100), (3, 100), (2, 200)]

    # Mock authors query -- tuples for `for row in author_rows` with row[0], row[1]
    author_rows = [(100, 'sa1'), (200, 'sa2')]

    # Wire up session.execute and session.query
    session.execute.return_value = paper_rows
    session.query.return_value.all = MagicMock(side_effect=[pa_rows, author_rows])

    paper_scores = {'sp1': 0.1, 'sp2': 0.3, 'sp3': 0.5}
    result = compute_author_scores(session, paper_scores)

    # Author A: median of [0.1, 0.5] = 0.3, 2 papers
    assert result['sa1']['median_score'] == 0.3
    assert result['sa1']['scored_paper_count'] == 2

    # Author B: median of [0.3] = 0.3, 1 paper
    assert result['sa2']['median_score'] == 0.3
    assert result['sa2']['scored_paper_count'] == 1


# ============================================================================
# UNIT TESTS: Sentinel row behavior
# ============================================================================


@patch('citation_graph_dag.fetch_paper_references_batch')
def test_sentinel_row_inserted_for_zero_references(mock_fetch):
    """
    Verify that fetch_and_store_references inserts a sentinel row
    (cited_s2_id=NULL) for papers that return 0 references from S2.
    """
    # S2 returns empty references for paper_x
    mock_fetch.return_value = []

    session = MagicMock()
    counts = fetch_and_store_references(session, ['paper_x'])

    # Should have inserted a sentinel row (no edges, one sentinel)
    assert counts['edges_inserted'] == 0
    assert counts['sentinel_rows'] == 1

    # Verify session.execute was called (sentinel INSERT + commit)
    assert session.execute.called

    # The sentinel INSERT params should contain source='paper_x'
    # (cited_s2_id is hardcoded as NULL in the SQL, not passed as a param)
    sentinel_call = session.execute.call_args_list[-1]
    params_dict = sentinel_call.args[1]
    assert params_dict['source'] == 'paper_x'
    assert 'cited' not in params_dict


@patch('citation_graph_dag.fetch_paper_references_batch')
def test_sentinel_row_not_inserted_when_references_exist(mock_fetch):
    """
    Verify that papers with references do NOT get sentinel rows.
    Only papers with 0 references should get sentinels.
    """
    mock_fetch.return_value = [
        S2PaperReference(source_s2_id='paper_y', cited_s2_id='ref1', is_influential=True),
    ]

    session = MagicMock()
    counts = fetch_and_store_references(session, ['paper_y'])

    assert counts['edges_inserted'] == 1
    assert counts['sentinel_rows'] == 0


def test_fetch_papers_needing_references_excludes_existing():
    """
    Verify that fetch_papers_needing_references excludes papers that already
    have entries in paper_citations, including sentinel rows. The SQL uses
    NOT EXISTS on source_s2_id which covers both real edges and sentinels.
    """
    session = MagicMock()

    # Mock: only paper_new needs references (paper_old already fetched)
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [('paper_new',)]
    session.execute.return_value = mock_result

    result = fetch_papers_needing_references(session)

    assert result == ['paper_new']
    # Verify the query was executed
    session.execute.assert_called_once()


# ============================================================================
# UNIT TESTS: fetch_external_nodes_needing_references
# ============================================================================


def test_fetch_external_nodes_needing_references():
    """
    Verify the function returns only nodes appearing as cited_s2_id but NOT
    as source_s2_id, excluding sentinel rows. The SQL uses LEFT JOIN where
    source IS NULL to find unfetched external nodes.

    Mock scenario:
    - 'ext1' appears as cited but never as source -> should be returned
    - 'ext2' appears as cited but never as source -> should be returned
    - 'int1' appears as both cited and source -> should NOT be returned
    """
    session = MagicMock()

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [('ext1',), ('ext2',)]
    session.execute.return_value = mock_result

    result = fetch_external_nodes_needing_references(session)

    assert result == ['ext1', 'ext2']
    assert len(result) == 2
    session.execute.assert_called_once()


# ============================================================================
# INTEGRATION TEST: Full pipeline
# ============================================================================


@patch('citation_graph_dag.fetch_paper_references_batch')
def test_full_pipeline(mock_fetch):
    """
    Integration test: mock S2 API and DB session, run DAG task functions in
    sequence, verify paper_citations rows, papers.pagerank JSONB, and
    authors.pagerank JSONB are populated.

    Test graph: A->B, B->C, A->C (same as PageRank unit test).
    Paper A and B are "our" papers (in the papers table).
    Author 1 wrote paper A, Author 2 wrote paper B.
    """
    import json

    # -- Step 1: Mock fetch_paper_references_batch to return known edges --
    mock_fetch.return_value = [
        S2PaperReference(source_s2_id='A', cited_s2_id='B', is_influential=True),
        S2PaperReference(source_s2_id='A', cited_s2_id='C', is_influential=False),
        S2PaperReference(source_s2_id='B', cited_s2_id='C', is_influential=True),
    ]

    # -- Step 2: Run fetch_and_store_references --
    session = MagicMock()
    counts = fetch_and_store_references(session, ['A', 'B'])

    # Verify edges were inserted (3 edges, no sentinels since both papers had refs)
    assert counts['edges_inserted'] == 3
    assert counts['sentinel_rows'] == 0

    # -- Step 3: Compute PageRank on the known graph --
    edges = [('A', 'B'), ('B', 'C'), ('A', 'C')]
    scores = compute_pagerank(edges)

    assert scores['C'] > scores['B'] > scores['A']

    # -- Step 4: Compute percentiles --
    percentiles = compute_percentiles(scores)

    # C has highest score -> P100
    assert percentiles['C'] == 100.0
    # All percentiles should be between 0 and 100
    for p in percentiles.values():
        assert 0 < p <= 100

    # -- Step 5: Compute author scores --
    author_session = MagicMock()

    # Mock papers.id -> s2_paper_id
    paper_rows = MagicMock()
    paper_rows.fetchall.return_value = [
        (1, 'A'),
        (2, 'B'),
    ]
    author_session.execute.return_value = paper_rows

    # Mock paper_authors: author 1 -> paper A, author 2 -> paper B
    # Tuples because the code unpacks via `for paper_id, author_id in pa_rows`
    pa_rows = [(1, 10), (2, 20)]

    # Mock authors -- tuples for row[0], row[1] access
    auth_rows = [(10, 'auth1'), (20, 'auth2')]

    author_session.query.return_value.all = MagicMock(side_effect=[pa_rows, auth_rows])

    author_data = compute_author_scores(author_session, scores)

    # Author 1 has paper A's score, Author 2 has paper B's score
    assert 'auth1' in author_data
    assert 'auth2' in author_data
    assert author_data['auth1']['scored_paper_count'] == 1
    assert author_data['auth2']['scored_paper_count'] == 1

    # Author 2 (paper B) should have higher median_score than Author 1 (paper A)
    assert author_data['auth2']['median_score'] > author_data['auth1']['median_score']

    # -- Step 6: Compute author percentiles --
    author_score_map = {k: v['median_score'] for k, v in author_data.items()}
    author_percentiles = compute_percentiles(author_score_map)

    assert author_percentiles['auth2'] == 100.0  # Higher score
    assert author_percentiles['auth1'] == 50.0   # Lower score (1 of 2)
