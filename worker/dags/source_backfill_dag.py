"""
Manual backfill for the source domain.

This DAG repairs source-owned metadata only:
- `arxiv_url`
- `published_at`
- `abstract`
"""

import asyncio
import re
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional

import pendulum
from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.arxiv.client import fetch_metadata
from shared.db import SessionLocal
from papers.db.models import PaperRecord


ARXIV_PUBLISHED_AT_BATCH_SIZE = 100
ARXIV_ABSTRACT_BATCH_SIZE = 100
ARXIV_URL_BATCH_SIZE = 500
ARXIV_API_BASE = 'http://export.arxiv.org/api/query'
ARXIV_API_DELAY = 3.0


@contextmanager
def database_session():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def fetch_published_dates_batch(arxiv_ids: List[str]) -> Dict[str, Optional[datetime]]:
    """Fetch published dates from arXiv for a batch of IDs."""
    import httpx

    id_list = ','.join(arxiv_ids)
    url = f"{ARXIV_API_BASE}?id_list={id_list}&max_results={len(arxiv_ids)}"
    response = httpx.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    ns = {'atom': 'http://www.w3.org/2005/Atom'}

    results: Dict[str, Optional[datetime]] = {}
    for entry in root.findall('atom:entry', ns):
        id_text = (entry.find('atom:id', ns).text or '').strip()
        match = re.search(r'/abs/([^/]+)', id_text)
        if not match:
            continue

        arxiv_id = re.sub(r'v\d+$', '', match.group(1))
        published_elem = entry.find('atom:published', ns)
        if published_elem is None or not published_elem.text:
            results[arxiv_id] = None
            continue

        try:
            results[arxiv_id] = datetime.fromisoformat(published_elem.text.strip().replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            results[arxiv_id] = None

    return results


def fetch_abstract_from_arxiv(arxiv_id: str) -> Optional[str]:
    """Fetch an abstract from arXiv with limited retry for rate limits."""
    import httpx

    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            metadata = asyncio.run(fetch_metadata(arxiv_id))
            time.sleep(ARXIV_API_DELAY)
            return metadata.summary if metadata else None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < max_retries:
                wait = ARXIV_API_DELAY * (attempt + 2)
                print(f'  429 for {arxiv_id}, waiting {wait}s (attempt {attempt + 1}/{max_retries})')
                time.sleep(wait)
                continue
            raise


@dag(
    dag_id='source_backfill',
    start_date=pendulum.datetime(2025, 1, 1, tz='UTC'),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'backfill', 'source'],
    doc_md="""
    ### Source Backfill

    Manual backfill aligned to the source ownership domain. It scans the current
    database for source-owned metadata that is missing and repairs it in-place.
    """,
)
def source_backfill_dag():

    @task
    def backfill_arxiv_urls() -> Dict[str, int]:
        with database_session() as session:
            rows = session.query(
                PaperRecord.paper_uuid,
                PaperRecord.arxiv_id,
            ).filter(
                PaperRecord.arxiv_url.is_(None),
                PaperRecord.arxiv_id.isnot(None),
            ).order_by(PaperRecord.id.asc()).all()

        total = len(rows)
        updated = 0
        failed = 0

        for i in range(0, total, ARXIV_URL_BATCH_SIZE):
            batch = rows[i:i + ARXIV_URL_BATCH_SIZE]
            with database_session() as session:
                for paper_uuid, arxiv_id in batch:
                    try:
                        record = session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()
                        if not record or not arxiv_id:
                            continue
                        record.arxiv_url = f'https://arxiv.org/abs/{arxiv_id}'
                        updated += 1
                    except Exception as exc:
                        print(f'  FAIL arxiv_url {paper_uuid}: {exc}')
                        failed += 1

        return {'total': total, 'updated': updated, 'failed': failed}

    @task
    def backfill_published_at() -> Dict[str, int]:
        with database_session() as session:
            rows = session.query(
                PaperRecord.id,
                PaperRecord.arxiv_id,
            ).filter(
                PaperRecord.arxiv_id.isnot(None),
                PaperRecord.published_at.is_(None),
            ).order_by(PaperRecord.id.asc()).all()

        total = len(rows)
        updated = 0
        failed = 0
        not_found = 0

        for i in range(0, total, ARXIV_PUBLISHED_AT_BATCH_SIZE):
            batch = rows[i:i + ARXIV_PUBLISHED_AT_BATCH_SIZE]
            arxiv_ids = [arxiv_id for _, arxiv_id in batch if arxiv_id]
            id_by_arxiv = {arxiv_id: paper_id for paper_id, arxiv_id in batch if arxiv_id}

            try:
                published_dates = fetch_published_dates_batch(arxiv_ids)
            except Exception as exc:
                print(f'  FAIL published_at batch {i // ARXIV_PUBLISHED_AT_BATCH_SIZE + 1}: {exc}')
                failed += len(batch)
                continue

            with database_session() as session:
                for arxiv_id in arxiv_ids:
                    paper_id = id_by_arxiv[arxiv_id]
                    published_at = published_dates.get(arxiv_id)
                    record = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
                    if not record:
                        continue
                    if published_at is None:
                        not_found += 1
                        continue
                    record.published_at = published_at
                    updated += 1

            time.sleep(ARXIV_API_DELAY)

        return {'total': total, 'updated': updated, 'failed': failed, 'not_found': not_found}

    @task
    def backfill_abstracts() -> Dict[str, int]:
        with database_session() as session:
            rows = session.query(
                PaperRecord.paper_uuid,
                PaperRecord.arxiv_id,
            ).filter(
                PaperRecord.arxiv_id.isnot(None),
                PaperRecord.abstract.is_(None),
            ).order_by(PaperRecord.id.asc()).all()

        total = len(rows)
        updated = 0
        failed = 0
        skipped = 0

        for i in range(0, total, ARXIV_ABSTRACT_BATCH_SIZE):
            batch = rows[i:i + ARXIV_ABSTRACT_BATCH_SIZE]
            print(f'Processing abstract batch {i // ARXIV_ABSTRACT_BATCH_SIZE + 1} with {len(batch)} papers...')

            for paper_uuid, arxiv_id in batch:
                if not arxiv_id:
                    skipped += 1
                    continue

                try:
                    abstract = fetch_abstract_from_arxiv(arxiv_id)
                    if not abstract:
                        skipped += 1
                        continue

                    with database_session() as session:
                        record = session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()
                        if record:
                            record.abstract = abstract
                            updated += 1
                except Exception as exc:
                    print(f'  FAIL abstract {paper_uuid} ({arxiv_id}): {exc}')
                    failed += 1

        return {'total': total, 'updated': updated, 'failed': failed, 'skipped': skipped}

    backfill_arxiv_urls() >> backfill_published_at() >> backfill_abstracts()


source_backfill_dag()
