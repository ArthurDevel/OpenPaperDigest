"""
Manual backfill for the processing domain.

This DAG repairs processing-owned artifacts and content-derived fields:
- `summaries`
- `embedding`
- `summaries.abstract_summary`
- `thumbnail.png` in storage
"""

import asyncio
import io
import os
import sys
from contextlib import contextmanager
from typing import Dict, List, Optional

import pendulum
from airflow.decorators import dag, task
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

sys.path.insert(0, '/opt/airflow')

import papers.storage as storage
from paperprocessor.embedding import generate_embedding
from papers.db.models import PaperRecord
from shared.db import SessionLocal


SUMMARY_BATCH_SIZE = 100
EMBEDDING_BATCH_SIZE = 100
ABSTRACT_SUMMARY_BATCH_SIZE = 100
THUMBNAIL_BATCH_SIZE = 100
ABSTRACT_SUMMARY_MAX_INPUT_WORDS = 1000


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


def get_markdown_for_paper(paper_uuid: str) -> Optional[str]:
    """Download a paper's stored markdown and return the first 1000 words."""
    try:
        stored = storage.download_paper_content(paper_uuid)
        if stored.final_markdown:
            words = stored.final_markdown.split()[:ABSTRACT_SUMMARY_MAX_INPUT_WORDS]
            return ' '.join(words)
    except Exception as exc:
        print(f'  Could not download markdown for {paper_uuid}: {exc}')
    return None


async def generate_abstract_summary_text(input_text: str) -> str:
    """Generate an abstract summary for processing-owned presentation fields."""
    from shared.openrouter.client import get_llm_response

    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'paperprocessor', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'generate_abstract_summary.md')

    with open(prompt_path, 'r', encoding='utf-8') as handle:
        system_prompt = handle.read()

    result = await get_llm_response(
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': input_text},
        ],
        model='google/gemini-3.1-flash-lite-preview',
    )

    summary_text = getattr(result, 'response_text', None)
    if not summary_text or not summary_text.strip():
        raise RuntimeError('LLM returned empty response')
    return summary_text.strip()


@dag(
    dag_id='processing_backfill',
    start_date=pendulum.datetime(2025, 1, 1, tz='UTC'),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['papers', 'backfill', 'processing'],
    doc_md="""
    ### Processing Backfill

    Manual backfill aligned to the processing ownership domain. It scans the
    current database and storage for processing-owned fields that are missing
    and repairs them in-place.
    """,
)
def processing_backfill_dag():

    @task
    def backfill_summaries() -> Dict[str, int]:
        with database_session() as session:
            rows = session.query(PaperRecord.paper_uuid).filter(
                PaperRecord.status.in_(['completed', 'partially_completed']),
                PaperRecord.summaries.is_(None),
            ).order_by(PaperRecord.id.asc()).all()

        paper_uuids = [row[0] for row in rows]
        updated = 0
        failed = 0

        for i in range(0, len(paper_uuids), SUMMARY_BATCH_SIZE):
            batch = paper_uuids[i:i + SUMMARY_BATCH_SIZE]
            with database_session() as session:
                for paper_uuid in batch:
                    try:
                        metadata = storage.download_metadata(paper_uuid)
                        summary = metadata.get('five_minute_summary')
                        if not summary:
                            continue

                        record = session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()
                        if not record:
                            continue

                        record.summaries = {'five_minute_summary': summary}
                        flag_modified(record, 'summaries')
                        updated += 1
                    except Exception as exc:
                        print(f'  FAIL summaries {paper_uuid}: {exc}')
                        failed += 1

        return {'total': len(paper_uuids), 'updated': updated, 'failed': failed}

    @task
    def backfill_embeddings() -> Dict[str, int]:
        with database_session() as session:
            rows = session.query(
                PaperRecord.paper_uuid,
                PaperRecord.title,
                PaperRecord.abstract,
            ).filter(
                PaperRecord.status.in_(['completed', 'partially_completed']),
                PaperRecord.embedding.is_(None),
            ).order_by(PaperRecord.id.asc()).all()

        updated = 0
        failed = 0
        skipped = 0

        for i in range(0, len(rows), EMBEDDING_BATCH_SIZE):
            batch = rows[i:i + EMBEDDING_BATCH_SIZE]
            for paper_uuid, title, abstract in batch:
                if not title:
                    skipped += 1
                    continue

                try:
                    embedding = asyncio.run(generate_embedding(title, abstract))
                    with database_session() as session:
                        record = session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()
                        if record:
                            record.embedding = embedding
                            updated += 1
                except Exception as exc:
                    print(f'  FAIL embedding {paper_uuid}: {exc}')
                    failed += 1

        return {'total': len(rows), 'updated': updated, 'failed': failed, 'skipped': skipped}

    @task
    def backfill_abstract_summaries() -> Dict[str, int]:
        with database_session() as session:
            rows = session.execute(
                text("""
                    SELECT paper_uuid, abstract, summaries
                    FROM papers
                    WHERE status IN ('completed', 'partially_completed')
                      AND (
                        summaries IS NULL
                        OR summaries->>'abstract_summary' IS NULL
                      )
                    ORDER BY id ASC
                """)
            ).fetchall()

        updated = 0
        failed = 0
        skipped = 0

        for i in range(0, len(rows), ABSTRACT_SUMMARY_BATCH_SIZE):
            batch = rows[i:i + ABSTRACT_SUMMARY_BATCH_SIZE]
            for paper_uuid, abstract, _summaries in batch:
                input_text = abstract
                if not input_text or (isinstance(input_text, str) and not input_text.strip()):
                    input_text = get_markdown_for_paper(paper_uuid)

                if not input_text:
                    skipped += 1
                    continue

                try:
                    summary = asyncio.run(generate_abstract_summary_text(input_text))
                    with database_session() as session:
                        record = session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()
                        if not record:
                            continue
                        summaries = dict(record.summaries or {})
                        summaries['abstract_summary'] = summary
                        record.summaries = summaries
                        flag_modified(record, 'summaries')
                        updated += 1
                except Exception as exc:
                    print(f'  FAIL abstract_summary {paper_uuid}: {exc}')
                    failed += 1

        return {'total': len(rows), 'updated': updated, 'failed': failed, 'skipped': skipped}

    @task
    def regenerate_missing_thumbnails() -> Dict[str, int]:
        import requests
        from pdf2image import convert_from_bytes
        from PIL import Image

        bucket = storage._bucket()
        with database_session() as session:
            rows = session.query(
                PaperRecord.paper_uuid,
                PaperRecord.arxiv_url,
            ).filter(
                PaperRecord.status == 'completed',
            ).order_by(PaperRecord.id.asc()).all()

        candidates: List[Dict[str, str]] = []
        for paper_uuid, arxiv_url in rows:
            try:
                bucket.download(f'{paper_uuid}/thumbnail.png')
            except Exception:
                if arxiv_url:
                    candidates.append({'paper_uuid': paper_uuid, 'arxiv_url': arxiv_url})

        success = 0
        failed = 0
        for i in range(0, len(candidates), THUMBNAIL_BATCH_SIZE):
            batch = candidates[i:i + THUMBNAIL_BATCH_SIZE]
            for paper_info in batch:
                paper_uuid = paper_info['paper_uuid']
                try:
                    pdf_url = paper_info['arxiv_url'].replace('/abs/', '/pdf/') + '.pdf'
                    response = requests.get(pdf_url, timeout=30)
                    response.raise_for_status()

                    images = convert_from_bytes(response.content, first_page=1, last_page=1, dpi=150)
                    first_page = images[0]
                    width, height = first_page.size
                    size = min(width, height)
                    thumbnail = first_page.crop((0, 0, size, size)).resize(
                        (400, 400),
                        Image.Resampling.LANCZOS,
                    )

                    buffer = io.BytesIO()
                    thumbnail.save(buffer, format='PNG')
                    bucket.upload(
                        f'{paper_uuid}/thumbnail.png',
                        buffer.getvalue(),
                        {'content-type': 'image/png', 'upsert': 'true'},
                    )
                    success += 1
                except Exception as exc:
                    print(f'  FAIL thumbnail {paper_uuid}: {exc}')
                    failed += 1

        return {'total': len(candidates), 'success': success, 'failed': failed}

    backfill_summaries() >> backfill_embeddings() >> backfill_abstract_summaries() >> regenerate_missing_thumbnails()


processing_backfill_dag()
