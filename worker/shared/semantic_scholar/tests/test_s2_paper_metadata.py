"""
Tests for S2 paper metadata DTOs and client batch-fetch logic.

Responsibilities:
- Verify S2PaperMetadata.to_s2_ids_dict() maps fields correctly and omits absent keys
- Verify S2PaperMetadata.to_s2_metrics_dict() maps fields correctly and omits absent keys
- Verify S2PaperMetadata.to_publication_info_dict() builds nested structure with None values omitted
- Verify fetch_paper_metadata_batch() parses mocked API responses into correct DTOs
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure worker root is on sys.path for imports like `shared.semantic_scholar`
WORKER_ROOT = Path(__file__).resolve().parents[3]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from shared.semantic_scholar.models import (
    S2PaperMetadata, S2FieldOfStudy, S2PublicationVenue, S2Journal, S2OpenAccessPdf,
)
from shared.semantic_scholar.client import fetch_paper_metadata_batch

# The DAG file imports airflow which isn't available in test env -- mock it
sys.modules.setdefault('airflow', MagicMock())
sys.modules.setdefault('airflow.decorators', MagicMock())

# Import needs the dags directory on sys.path
DAGS_DIR = WORKER_ROOT / 'dags'
if str(DAGS_DIR) not in sys.path:
    sys.path.insert(0, str(DAGS_DIR))


# ============================================================================
# CONSTANTS
# ============================================================================

FULL_METADATA = S2PaperMetadata(
    paper_id='abc123def456',
    arxiv_id='2301.00001',
    corpus_id=987654,
    external_ids={
        'ArXiv': '2301.00001',
        'DOI': '10.1234/example.2025.001',
        'PMID': '12345678',
        'PMCID': 'PMC1234567',
        'DBLP': 'conf/neurips/SmithJones2025',
        'MAG': '2987654321',
        'ACL': '2025.acl-long.123',
    },
    citation_count=342,
    reference_count=45,
    influential_citation_count=28,
    s2_fields_of_study=[
        S2FieldOfStudy(category='Computer Science', source='external'),
        S2FieldOfStudy(category='NLP', source='s2-fos-model'),
    ],
    publication_types=['Conference', 'Journal Article'],
    venue='NeurIPS',
    publication_venue=S2PublicationVenue(
        id='venue-001',
        name='Neural Information Processing Systems',
        type='conference',
        alternate_names=['NeurIPS', 'NIPS'],
        url='https://neurips.cc',
    ),
    journal=S2Journal(name='Nature MI', volume='7', pages='102-115'),
    year=2025,
    publication_date='2025-12-10',
    tldr='A one-line summary of the paper.',
    is_open_access=True,
    open_access_pdf=S2OpenAccessPdf(url='https://example.com/paper.pdf', status='GREEN'),
    embedding=[0.1] * 768,
)

PARTIAL_METADATA = S2PaperMetadata(
    paper_id='partial789',
    external_ids={'DOI': '10.9999/partial'},
)

# Mock S2 API response: 3 items (full paper, partial paper, null entry)
MOCK_BATCH_RESPONSE = [
    # Full paper
    {
        'paperId': 'abc123def456',
        'corpusId': 987654,
        'externalIds': {
            'ArXiv': '2301.00001',
            'DOI': '10.1234/example.2025.001',
            'PMID': '12345678',
        },
        'citationCount': 342,
        'referenceCount': 45,
        'influentialCitationCount': 28,
        's2FieldsOfStudy': [
            {'category': 'Computer Science', 'source': 'external'},
        ],
        'publicationTypes': ['Conference'],
        'venue': 'NeurIPS',
        'publicationVenue': {
            'id': 'venue-001',
            'name': 'Neural Information Processing Systems',
            'type': 'conference',
            'alternateNames': ['NeurIPS', 'NIPS'],
            'url': 'https://neurips.cc',
        },
        'journal': {'name': 'Nature MI', 'volume': '7', 'pages': '102-115'},
        'year': 2025,
        'publicationDate': '2025-12-10',
        'tldr': {'model': 'tldr@v2.0.0', 'text': 'A great paper summary.'},
        'isOpenAccess': True,
        'openAccessPdf': {'url': 'https://example.com/paper.pdf', 'status': 'GREEN'},
        'embedding': {'model': 'specter_v2', 'vector': [0.5, 0.6, 0.7]},
    },
    # Null entry (paper not found by S2)
    None,
    # Partial paper (minimal fields)
    {
        'paperId': 'partial789',
        'corpusId': None,
        'externalIds': {'ArXiv': '2301.00003'},
        'citationCount': None,
        'referenceCount': None,
        'influentialCitationCount': None,
        's2FieldsOfStudy': None,
        'publicationTypes': None,
        'venue': '',
        'publicationVenue': None,
        'journal': None,
        'year': None,
        'publicationDate': None,
        'tldr': None,
        'isOpenAccess': None,
        'openAccessPdf': None,
        'embedding': None,
    },
]


# ============================================================================
# DTO MAPPING TESTS
# ============================================================================


def test_to_s2_ids_dict_full():
    """All fields populated -- verify correct key mapping from PascalCase to lowercase."""
    result = FULL_METADATA.to_s2_ids_dict()

    assert result == {
        's2_paper_id': 'abc123def456',
        's2_corpus_id': 987654,
        'doi': '10.1234/example.2025.001',
        'pmid': '12345678',
        'pmcid': 'PMC1234567',
        'dblp': 'conf/neurips/SmithJones2025',
        'mag': '2987654321',
        'acl': '2025.acl-long.123',
    }


def test_to_s2_ids_dict_partial():
    """Only paper_id + DOI -- verify other keys are omitted."""
    result = PARTIAL_METADATA.to_s2_ids_dict()

    assert result == {
        's2_paper_id': 'partial789',
        'doi': '10.9999/partial',
    }
    # Keys that should NOT be present
    assert 's2_corpus_id' not in result
    assert 'pmid' not in result
    assert 'mag' not in result


def test_to_s2_ids_dict_empty_external_ids():
    """Empty external_ids dict -- only paper_id should be present."""
    meta = S2PaperMetadata(paper_id='empty123', external_ids={})
    result = meta.to_s2_ids_dict()

    assert result == {'s2_paper_id': 'empty123'}
    assert 'doi' not in result
    assert 'pmid' not in result


def test_to_s2_metrics_dict_full():
    """Full metrics -- all three counts present."""
    result = FULL_METADATA.to_s2_metrics_dict()

    assert result == {
        'citation_count': 342,
        'reference_count': 45,
        'influential_citation_count': 28,
    }


def test_to_s2_metrics_dict_partial():
    """Partial metadata with no counts -- returns empty dict."""
    result = PARTIAL_METADATA.to_s2_metrics_dict()

    assert result == {}


def test_to_publication_info_dict():
    """Full case with all nested objects -- verify nested dicts omit None values."""
    result = FULL_METADATA.to_publication_info_dict()

    assert result['venue'] == 'NeurIPS'
    assert result['year'] == 2025
    assert result['publication_date'] == '2025-12-10'
    assert result['is_open_access'] is True

    # Nested publication_venue
    pv = result['publication_venue']
    assert pv['id'] == 'venue-001'
    assert pv['name'] == 'Neural Information Processing Systems'
    assert pv['type'] == 'conference'
    assert pv['alternate_names'] == ['NeurIPS', 'NIPS']
    assert pv['url'] == 'https://neurips.cc'

    # Nested journal
    j = result['journal']
    assert j['name'] == 'Nature MI'
    assert j['volume'] == '7'
    assert j['pages'] == '102-115'

    # Nested open_access_pdf
    oa = result['open_access_pdf']
    assert oa['url'] == 'https://example.com/paper.pdf'
    assert oa['status'] == 'GREEN'


def test_to_publication_info_dict_partial():
    """Partial metadata with no publication info -- returns empty dict."""
    result = PARTIAL_METADATA.to_publication_info_dict()

    assert result == {}


def test_to_publication_info_dict_empty_nested_objects():
    """Nested objects with all None fields should be omitted from the result."""
    meta = S2PaperMetadata(
        paper_id='empty-nested',
        venue='NeurIPS',
        publication_venue=S2PublicationVenue(),  # all fields None
        journal=S2Journal(),                     # all fields None
        open_access_pdf=S2OpenAccessPdf(),       # all fields None
        year=2025,
    )
    result = meta.to_publication_info_dict()

    assert result['venue'] == 'NeurIPS'
    assert result['year'] == 2025
    # Empty nested objects should not appear
    assert 'publication_venue' not in result
    assert 'journal' not in result
    assert 'open_access_pdf' not in result


# ============================================================================
# CLIENT TESTS
# ============================================================================


@patch('shared.semantic_scholar.client._request_with_retry')
def test_fetch_paper_metadata_batch(mock_request):
    """
    Mock _request_with_retry and verify:
    - Null entries are skipped (2 results from 3 items)
    - Full paper fields are populated correctly
    - Partial paper has None for missing fields
    - arxiv_id is extracted from externalIds.ArXiv
    - tldr is extracted as text string from {"model": ..., "text": ...}
    - embedding is extracted from {"vector": [...]}
    """
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_BATCH_RESPONSE
    mock_request.return_value = mock_response

    arxiv_ids = ['2301.00001', '2301.00002', '2301.00003']
    results = fetch_paper_metadata_batch(arxiv_ids)

    # Null entry skipped -- 2 DTOs returned
    assert len(results) == 2

    # -- Full paper --
    full = results[0]
    assert full.paper_id == 'abc123def456'
    assert full.corpus_id == 987654
    assert full.arxiv_id == '2301.00001'
    assert full.citation_count == 342
    assert full.reference_count == 45
    assert full.influential_citation_count == 28
    assert full.venue == 'NeurIPS'
    assert full.year == 2025
    assert full.publication_date == '2025-12-10'
    assert full.is_open_access is True

    # externalIds mapped
    assert full.external_ids['DOI'] == '10.1234/example.2025.001'
    assert full.external_ids['PMID'] == '12345678'

    # tldr extracted as text string (not the full object)
    assert full.tldr == 'A great paper summary.'

    # embedding extracted from {"vector": [...]}
    assert full.embedding == [0.5, 0.6, 0.7]

    # Nested objects parsed
    assert len(full.s2_fields_of_study) == 1
    assert full.s2_fields_of_study[0].category == 'Computer Science'
    assert full.publication_venue.name == 'Neural Information Processing Systems'
    assert full.publication_venue.alternate_names == ['NeurIPS', 'NIPS']
    assert full.journal.name == 'Nature MI'
    assert full.open_access_pdf.url == 'https://example.com/paper.pdf'

    # -- Partial paper --
    partial = results[1]
    assert partial.paper_id == 'partial789'
    assert partial.arxiv_id == '2301.00003'
    assert partial.corpus_id is None
    assert partial.citation_count is None
    assert partial.reference_count is None
    assert partial.s2_fields_of_study is None
    assert partial.publication_types is None
    assert partial.venue is None
    assert partial.journal is None
    assert partial.tldr is None
    assert partial.embedding is None


# ============================================================================
# BUILD CLASSIFICATION DICT TESTS
# ============================================================================


def test_build_classification_dict_merges_arxiv_and_s2():
    """
    Verify that build_classification_dict:
    - Preserves existing arxiv_categories
    - Adds s2_fields_of_study correctly
    - Adds s2_publication_types
    - Omits keys when S2 values are None
    """
    from enrich_s2_paper_data_dag import build_classification_dict

    # Simulate a PaperRecord with existing arXiv classification
    mock_record = MagicMock()
    mock_record.classification = {
        'arxiv_categories': ['cs.CL', 'cs.AI'],
        'arxiv_doi': '10.1234/example',
    }

    s2_meta = S2PaperMetadata(
        paper_id='abc123',
        s2_fields_of_study=[
            S2FieldOfStudy(category='Computer Science', source='external'),
            S2FieldOfStudy(category='NLP', source='s2-fos-model'),
        ],
        publication_types=['Conference', 'Journal Article'],
    )

    result = build_classification_dict(mock_record, s2_meta)

    # Existing arxiv keys preserved
    assert result['arxiv_categories'] == ['cs.CL', 'cs.AI']
    assert result['arxiv_doi'] == '10.1234/example'

    # S2 fields added
    assert result['s2_fields_of_study'] == [
        {'category': 'Computer Science', 'source': 'external'},
        {'category': 'NLP', 'source': 's2-fos-model'},
    ]
    assert result['s2_publication_types'] == ['Conference', 'Journal Article']


def test_build_classification_dict_none_values_omitted():
    """
    When S2 metadata has no fields_of_study or publication_types,
    those keys should not appear in the result.
    """
    from enrich_s2_paper_data_dag import build_classification_dict

    mock_record = MagicMock()
    mock_record.classification = {'arxiv_categories': ['cs.LG']}

    s2_meta = S2PaperMetadata(
        paper_id='xyz789',
        s2_fields_of_study=None,
        publication_types=None,
    )

    result = build_classification_dict(mock_record, s2_meta)

    # Existing key preserved
    assert result['arxiv_categories'] == ['cs.LG']

    # S2 keys not added since values are None
    assert 's2_fields_of_study' not in result
    assert 's2_publication_types' not in result


def test_build_classification_dict_no_existing_classification():
    """
    When paper has no existing classification (None), start from empty dict
    and add S2 data.
    """
    from enrich_s2_paper_data_dag import build_classification_dict

    mock_record = MagicMock()
    mock_record.classification = None

    s2_meta = S2PaperMetadata(
        paper_id='new456',
        s2_fields_of_study=[
            S2FieldOfStudy(category='Mathematics', source='external'),
        ],
        publication_types=['Conference'],
    )

    result = build_classification_dict(mock_record, s2_meta)

    assert result['s2_fields_of_study'] == [
        {'category': 'Mathematics', 'source': 'external'},
    ]
    assert result['s2_publication_types'] == ['Conference']
    assert 'arxiv_categories' not in result
