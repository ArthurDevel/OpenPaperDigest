"""
Tests for arXiv classification dict building logic used during paper ingestion.

Verifies that build_arxiv_classification_dict correctly:
- Includes arxiv_categories, arxiv_primary_category, arxiv_doi, arxiv_journal_ref when present
- Omits keys when values are absent or empty
"""

import sys
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import httpx
import pendulum

# Ensure worker root is on sys.path for imports like `shared.arxiv`
WORKER_ROOT = Path(__file__).resolve().parents[3]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

# Mock airflow and other DAG-only dependencies before importing the DAG module
sys.modules.setdefault('airflow', MagicMock())
sys.modules.setdefault('airflow.decorators', MagicMock())

from dags.daily_arxiv_ingest_dag import (
    ARXIV_API_BASE,
    build_arxiv_classification_dict,
    fetch_new_arxiv_papers,
)


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


def test_fetch_new_arxiv_papers_retries_after_429(monkeypatch):
    request = httpx.Request(
        'GET',
        f'{ARXIV_API_BASE}?search_query=cat:cs.*+AND+submittedDate:[202604080000+TO+202604102359]&start=0&max_results=2&sortBy=submittedDate&sortOrder=descending',
    )
    rate_limited = httpx.Response(
        429,
        request=request,
        headers={'Retry-After': '7'},
        content=b'rate limited',
    )
    success = httpx.Response(
        200,
        request=request,
        content=b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2604.12345v1</id>
    <title>Retry-safe ingest</title>
    <summary>Abstract text</summary>
    <author><name>Alice Example</name></author>
    <category term="cs.AI" />
    <published>2026-04-09T12:00:00Z</published>
  </entry>
</feed>
""",
    )

    responses = iter([rate_limited, success])
    sleeps: List[float] = []

    monkeypatch.setattr('dags.daily_arxiv_ingest_dag.pendulum.now', lambda _tz: pendulum.datetime(2026, 4, 10, tz='UTC'))
    monkeypatch.setattr(httpx, 'get', lambda *args, **kwargs: next(responses))
    monkeypatch.setattr('dags.daily_arxiv_ingest_dag.time.sleep', lambda seconds: sleeps.append(seconds))

    papers = fetch_new_arxiv_papers(max_results=2)

    assert len(papers) == 1
    assert papers[0]['arxiv_id'] == '2604.12345'
    assert papers[0]['title'] == 'Retry-safe ingest'
    assert sleeps == [7.0]
