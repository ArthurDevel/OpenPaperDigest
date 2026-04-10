"""
Backfill published_at DAG -- fetches arXiv publication dates for existing papers.

Queries the arXiv API in batches to retrieve the <published> timestamp for each
paper that has an arxiv_id but no published_at value. Manual trigger only.
"""

import sys
import time
import pendulum
import xml.etree.ElementTree as ET
from datetime import datetime
from airflow.decorators import dag, task
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

sys.path.insert(0, '/opt/airflow')

from sqlalchemy.orm import Session
from shared.db import SessionLocal
from papers.db.models import PaperRecord

# arXiv API settings
ARXIV_API_BASE = 'http://export.arxiv.org/api/query'
BATCH_SIZE = 100  # IDs per arXiv API call (max ~200, keep conservative)
API_DELAY = 3.0   # seconds between API calls (arXiv rate limit)


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
    """
    Fetch published dates from arXiv API for a batch of IDs.

    @param arxiv_ids: List of arXiv identifiers
    @returns Dict mapping arxiv_id -> published_at datetime (or None if not found)
    """
    import httpx

    id_list = ','.join(arxiv_ids)
    url = f"{ARXIV_API_BASE}?id_list={id_list}&max_results={len(arxiv_ids)}"

    response = httpx.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    ns = {'atom': 'http://www.w3.org/2005/Atom'}

    results: Dict[str, Optional[datetime]] = {}

    for entry in root.findall('atom:entry', ns):
        # Extract arxiv_id from entry id URL (http://arxiv.org/abs/2501.12345v1)
        id_text = (entry.find('atom:id', ns).text or '').strip()
        import re
        m = re.search(r'/abs/([^/]+)', id_text)
        if not m:
            continue
        arxiv_id = re.sub(r'v\d+$', '', m.group(1))

        published_elem = entry.find('atom:published', ns)
        if published_elem is not None and published_elem.text:
            try:
                pub_str = published_elem.text.strip()
                published_at = datetime.fromisoformat(pub_str.replace('Z', '+00:00'))
                results[arxiv_id] = published_at
            except (ValueError, AttributeError):
                results[arxiv_id] = None
        else:
            results[arxiv_id] = None

    return results


@dag(
    dag_id="deprecated_backfill_published_at",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    tags=["backfill", "maintenance"],
    description="Backfill published_at for papers using arXiv API",
)
def backfill_published_at():
    """
    Fetch arXiv publication dates for all papers missing published_at.
    Queries the DB directly (no XCom) and processes in batches with rate
    limiting to respect arXiv API limits.
    """

    @task
    def backfill_dates() -> Dict[str, Any]:
        updated = 0
        failed = 0
        not_found = 0
        offset = 0

        # Count total for logging
        with database_session() as session:
            total = session.query(PaperRecord.id).filter(
                PaperRecord.arxiv_id.isnot(None),
                PaperRecord.published_at.is_(None),
            ).count()
        print(f"Found {total} papers missing published_at")

        while True:
            # Fetch one batch of papers directly from the DB each iteration
            with database_session() as session:
                batch = session.query(PaperRecord.id, PaperRecord.arxiv_id).filter(
                    PaperRecord.arxiv_id.isnot(None),
                    PaperRecord.published_at.is_(None),
                ).order_by(PaperRecord.id.desc()).limit(BATCH_SIZE).offset(offset).all()

            if not batch:
                break

            arxiv_ids = [p.arxiv_id for p in batch]
            id_to_db_id = {p.arxiv_id: p.id for p in batch}

            try:
                date_map = fetch_published_dates_batch(arxiv_ids)
            except Exception as e:
                batch_num = offset // BATCH_SIZE + 1
                print(f"  Batch {batch_num} API error: {e}")
                failed += len(batch)
                offset += BATCH_SIZE
                time.sleep(API_DELAY)
                continue

            with database_session() as session:
                for arxiv_id, published_at in date_map.items():
                    db_id = id_to_db_id.get(arxiv_id)
                    if not db_id:
                        continue
                    if published_at is None:
                        not_found += 1
                        continue
                    session.query(PaperRecord).filter(
                        PaperRecord.id == db_id
                    ).update({"published_at": published_at})
                    updated += 1

            # Rows that got updated are no longer returned by the query,
            # so only advance offset for rows that weren't updated
            batch_not_updated = len(batch) - sum(
                1 for aid in arxiv_ids
                if date_map.get(aid) is not None
            )
            offset += batch_not_updated

            batch_num = (updated + not_found + failed + batch_not_updated) // BATCH_SIZE
            if batch_num % 10 == 0:
                print(f"  Progress: {updated} updated, {not_found} not found, {failed} failed")

            time.sleep(API_DELAY)

        summary = {
            "total": total,
            "updated": updated,
            "not_found": not_found,
            "failed": failed,
        }
        print(f"Backfill complete: {summary}")
        return summary

    backfill_dates()


backfill_published_at_dag = backfill_published_at()
