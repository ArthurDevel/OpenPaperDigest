"""
Backfill abstract summaries for existing papers.

One-time Airflow DAG that generates short 2-3 sentence abstract summaries
for all completed/partially_completed papers that don't have one yet.
Uses the paper's abstract if available, otherwise falls back to the first
1000 words of the stored markdown content.

Responsibilities:
- Query papers missing abstract_summary in their summaries JSON
- Generate abstract summary via Gemini Flash (OpenRouter)
- Save each summary immediately (crash-safe)
- Generate summary report
"""

import sys
import asyncio
import pendulum
from typing import List, Dict, Optional

from airflow.decorators import dag, task
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import text

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord

# ============================================================================
# CONSTANTS
# ============================================================================

FETCH_BATCH_SIZE = 100
ABSTRACT_SUMMARY_MAX_INPUT_WORDS = 1000
CONCURRENCY = 20


def fetch_papers_without_abstract_summary(session: Session, batch_size: int = FETCH_BATCH_SIZE) -> List[Dict]:
    """
    Query completed/partially_completed papers where summaries JSON has no abstract_summary.

    @param session: SQLAlchemy session to use
    @param batch_size: Maximum number of papers to fetch per query
    @returns List of dicts with paper_uuid, abstract, and summaries
    """
    # Use raw SQL to filter on JSONB key absence
    rows = session.execute(
        text("""
            SELECT paper_uuid, abstract, summaries
            FROM papers
            WHERE status IN ('completed', 'partially_completed')
            AND (
                summaries IS NULL
                OR summaries->>'abstract_summary' IS NULL
            )
            ORDER BY id DESC
            LIMIT :batch_size
        """),
        {"batch_size": batch_size}
    ).fetchall()

    return [
        {
            "paper_uuid": row[0],
            "abstract": row[1],
            "summaries": row[2],
        }
        for row in rows
    ]


def get_markdown_for_paper(paper_uuid: str) -> Optional[str]:
    """
    Download the first 1000 words of stored markdown for a paper.
    Returns None if download fails.

    @param paper_uuid: Paper UUID to download markdown for
    @returns First 1000 words of markdown, or None
    """
    try:
        import papers.storage as storage
        stored = storage.download_paper_content(paper_uuid)
        # v2 papers (pipeline_version=2) have empty final_markdown -- they get
        # their abstract summary during processing, so returning None here
        # correctly skips them in the backfill
        if stored.final_markdown:
            words = stored.final_markdown.split()[:ABSTRACT_SUMMARY_MAX_INPUT_WORDS]
            return " ".join(words)
    except Exception as e:
        print(f"  Could not download markdown for {paper_uuid}: {e}")
    return None


async def generate_abstract_summary_text(input_text: str) -> str:
    """
    Generate a 2-3 sentence abstract summary from input text using Gemini Flash.

    @param input_text: Abstract or opening text to summarize
    @returns Generated summary text

    Raises:
        RuntimeError: If LLM returns empty response
    """
    import os
    from shared.openrouter.client import get_llm_response

    # Load prompt
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'paperprocessor', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'generate_abstract_summary.md')

    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    result = await get_llm_response(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": input_text},
        ],
        model="google/gemini-3.1-flash-lite-preview",
    )

    summary_text = getattr(result, "response_text", None)
    if not summary_text or summary_text.strip() == "":
        raise RuntimeError("LLM returned empty response")

    return summary_text.strip()


def save_abstract_summary(session: Session, paper_uuid: str, abstract_summary: str) -> None:
    """
    Update the summaries JSON column to include abstract_summary.
    Merges with existing summaries (preserves five_minute_summary if present).
    Commits immediately to ensure crash-safety.

    @param session: SQLAlchemy session to use
    @param paper_uuid: Paper UUID to update
    @param abstract_summary: Generated abstract summary text
    """
    record = session.query(PaperRecord).filter(
        PaperRecord.paper_uuid == paper_uuid
    ).first()
    if record:
        existing = dict(record.summaries or {})
        existing["abstract_summary"] = abstract_summary
        record.summaries = existing
        flag_modified(record, "summaries")
        session.commit()


# ============================================================================
# DAG DEFINITION
# ============================================================================


@dag(
    dag_id="backfill_abstract_summaries",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time"],
    doc_md="""
    ### Backfill Abstract Summaries DAG

    **ONE-TIME USE DAG**: Generates short 2-3 sentence abstract summaries
    for all completed/partially_completed papers that don't have one yet.

    Uses the paper's abstract if available, otherwise downloads the stored
    markdown and uses the first 1000 words. Each summary is saved immediately
    after generation (crash-safe).
    """,
)
def backfill_abstract_summaries_dag():

    @task
    def process_all_papers() -> Dict[str, int]:
        """
        Loop through all papers without abstract summaries, generate and save concurrently.
        Processes up to CONCURRENCY papers in parallel per batch.

        @returns Dict with total/updated/failed/skipped counts
        """

        async def process_single_paper(
            semaphore: asyncio.Semaphore, session: Session, paper: Dict, counters: Dict[str, int]
        ) -> None:
            """Process a single paper with semaphore-based concurrency control."""
            async with semaphore:
                paper_uuid = paper["paper_uuid"]
                abstract = paper["abstract"]

                # Determine input text
                input_text = abstract
                if not input_text or (isinstance(input_text, str) and input_text.strip() == ""):
                    input_text = get_markdown_for_paper(paper_uuid)

                if not input_text:
                    print(f"  SKIP {paper_uuid}: no abstract and no markdown available")
                    counters["skipped"] += 1
                    return

                try:
                    summary = await generate_abstract_summary_text(input_text)
                    save_abstract_summary(session, paper_uuid, summary)
                    counters["updated"] += 1
                except Exception as e:
                    print(f"  FAIL {paper_uuid}: {e}")
                    counters["failed"] += 1

                if counters["updated"] % 50 == 0 and counters["updated"] > 0:
                    print(f"  Progress: {counters['updated']} abstract summaries saved")

        async def run() -> Dict[str, int]:
            counters = {"total": 0, "updated": 0, "failed": 0, "skipped": 0}
            semaphore = asyncio.Semaphore(CONCURRENCY)
            session: Session = SessionLocal()

            try:
                while True:
                    papers = fetch_papers_without_abstract_summary(session, batch_size=FETCH_BATCH_SIZE)
                    if not papers:
                        break

                    counters["total"] += len(papers)
                    print(f"Fetched batch of {len(papers)} papers (total so far: {counters['total']})")

                    tasks = [process_single_paper(semaphore, session, paper, counters) for paper in papers]
                    await asyncio.gather(*tasks)
            finally:
                session.close()

            print("\n" + "=" * 50)
            print("BACKFILL ABSTRACT SUMMARIES REPORT")
            print("=" * 50)
            print(f"Total papers:  {counters['total']}")
            print(f"Updated:       {counters['updated']}")
            print(f"Failed:        {counters['failed']}")
            print(f"Skipped:       {counters['skipped']}")
            print("=" * 50)

            return counters

        return asyncio.run(run())

    process_all_papers()


backfill_abstract_summaries_dag()
