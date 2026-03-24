"""
Tests for arXiv classification dict building logic used during paper ingestion.

Verifies that build_arxiv_classification_dict correctly:
- Includes arxiv_categories, arxiv_primary_category, arxiv_doi, arxiv_journal_ref when present
- Omits keys when values are absent or empty
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure worker root is on sys.path for imports like `shared.arxiv`
WORKER_ROOT = Path(__file__).resolve().parents[3]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

# Mock airflow and other DAG-only dependencies before importing the DAG module
sys.modules.setdefault('airflow', MagicMock())
sys.modules.setdefault('airflow.decorators', MagicMock())

from dags.daily_arxiv_ingest_dag import build_arxiv_classification_dict


class TestBuildArxivClassificationDict:
    """Tests for build_arxiv_classification_dict()."""

    def test_full_metadata(self):
        """All fields present produces complete classification dict."""
        paper = {
            'categories': ['cs.CL', 'cs.AI', 'cs.LG'],
            'doi': '10.1234/example.2025.001',
            'journal_ref': 'Nature 2025',
        }
        result = build_arxiv_classification_dict(paper)
        assert result == {
            'arxiv_categories': ['cs.CL', 'cs.AI', 'cs.LG'],
            'arxiv_primary_category': 'cs.CL',
            'arxiv_doi': '10.1234/example.2025.001',
            'arxiv_journal_ref': 'Nature 2025',
        }

    def test_categories_only(self):
        """Missing doi and journal_ref are omitted from the dict."""
        paper = {
            'categories': ['cs.CV'],
            'doi': None,
            'journal_ref': None,
        }
        result = build_arxiv_classification_dict(paper)
        assert result == {
            'arxiv_categories': ['cs.CV'],
            'arxiv_primary_category': 'cs.CV',
        }
        assert 'arxiv_doi' not in result
        assert 'arxiv_journal_ref' not in result

    def test_empty_categories(self):
        """Empty categories list omits arxiv_categories and arxiv_primary_category."""
        paper = {
            'categories': [],
            'doi': '10.5555/test',
            'journal_ref': None,
        }
        result = build_arxiv_classification_dict(paper)
        assert result == {
            'arxiv_doi': '10.5555/test',
        }
        assert 'arxiv_categories' not in result
        assert 'arxiv_primary_category' not in result

    def test_no_metadata_at_all(self):
        """Paper dict with no classification fields returns empty dict."""
        paper = {
            'arxiv_id': '2503.12345',
            'title': 'Some paper',
        }
        result = build_arxiv_classification_dict(paper)
        assert result == {}

    def test_empty_string_values_omitted(self):
        """Empty string doi/journal_ref are treated as absent."""
        paper = {
            'categories': ['stat.ML'],
            'doi': '',
            'journal_ref': '',
        }
        result = build_arxiv_classification_dict(paper)
        assert result == {
            'arxiv_categories': ['stat.ML'],
            'arxiv_primary_category': 'stat.ML',
        }
