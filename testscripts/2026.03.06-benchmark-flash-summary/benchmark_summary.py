"""
Benchmark 5-minute summary generation using google/gemini-3-flash-preview.

Fetches a few real papers from the DB, downloads their content.md from
Supabase Storage, generates summaries with Flash vs Pro, and reports
time + cost per paper.

Usage:
    cd worker
    python ../testscripts/2026.03.06-benchmark-flash-summary/benchmark_summary.py
"""

import asyncio
import os
import sys
import time

# Allow running from repo root or from worker/
worker_dir = os.path.join(os.path.dirname(__file__), "..", "..", "worker")
sys.path.insert(0, os.path.abspath(worker_dir))

from dotenv import load_dotenv

load_dotenv(os.path.join(worker_dir, ".env"))

from shared.openrouter.client import get_llm_response
from papers.storage import download_markdown

FLASH_MODEL = "google/gemini-3-flash-preview"
CURRENT_MODEL = "google/gemini-2.5-pro"
PROMPT_PATH = os.path.join(
    worker_dir, "paperprocessor", "prompts", "generate_5min_summary.md"
)
NUM_PAPERS = 5


def load_system_prompt() -> str:
    with open(PROMPT_PATH, "r") as f:
        return f.read()


def fetch_completed_papers(limit: int):
    """Fetch completed papers from the DB."""
    from sqlalchemy import create_engine, text

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT paper_uuid, title "
                "FROM papers "
                "WHERE status = 'completed' "
                "ORDER BY random() "
                "LIMIT :limit"
            ),
            {"limit": limit},
        ).fetchall()
    return rows


async def generate_summary(system_prompt: str, final_markdown: str, model: str):
    """Generate a summary and return the result with timing."""
    start = time.time()
    result = await get_llm_response(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_markdown},
        ],
        model=model,
    )
    elapsed = time.time() - start
    return result, elapsed


async def main():
    system_prompt = load_system_prompt()
    print(f"Fetching {NUM_PAPERS} random processed papers from DB...")
    papers = fetch_completed_papers(NUM_PAPERS)

    if not papers:
        print("No processed papers found in DB.")
        return

    # Download content.md for each paper from Supabase Storage
    print(f"Found {len(papers)} papers. Downloading content.md from storage...")
    paper_data = []
    for paper_uuid, title in papers:
        try:
            markdown = download_markdown(paper_uuid)
            paper_data.append((paper_uuid, title, len(markdown), markdown))
            print(f"  {title[:60]}... ({len(markdown):,} chars)")
        except Exception as e:
            print(f"  SKIP {title[:60]}... (no content.md: {e})")

    if not paper_data:
        print("No papers with content.md found in storage.")
        return

    print(f"\nReady to benchmark {len(paper_data)} papers.")
    print("=" * 80)

    models = [FLASH_MODEL, CURRENT_MODEL]

    for model in models:
        print(f"\n{'=' * 80}")
        print(f"MODEL: {model}")
        print(f"{'=' * 80}")

        total_time = 0.0
        total_cost = 0.0
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for i, (paper_uuid, title, md_len, final_markdown) in enumerate(paper_data):
            print(f"\n--- Paper {i + 1}/{len(paper_data)} ---")
            print(f"  Title:    {title[:80]}")
            print(f"  MD size:  {md_len:,} chars")

            result, elapsed = await generate_summary(
                system_prompt, final_markdown, model
            )

            # Cost is available inline in usage.cost (more reliable than generation lookup)
            cost = result.raw_response.get("usage", {}).get("cost") or result.cost_info.total_cost or 0.0
            prompt_tok = result.cost_info.prompt_tokens or 0
            compl_tok = result.cost_info.completion_tokens or 0
            summary_len = len(result.response_text or "")

            total_time += elapsed
            total_cost += cost
            total_prompt_tokens += prompt_tok
            total_completion_tokens += compl_tok

            print(f"  Time:     {elapsed:.1f}s")
            print(f"  Tokens:   {prompt_tok:,} prompt + {compl_tok:,} completion")
            print(f"  Cost:     ${cost:.6f}")
            print(f"  Summary:  {summary_len:,} chars")

        print(f"\n{'─' * 60}")
        print(f"TOTALS for {model}:")
        print(f"  Papers:       {len(paper_data)}")
        print(f"  Total time:   {total_time:.1f}s (avg {total_time / len(paper_data):.1f}s)")
        print(f"  Total cost:   ${total_cost:.6f} (avg ${total_cost / len(paper_data):.6f})")
        print(
            f"  Total tokens: {total_prompt_tokens + total_completion_tokens:,} "
            f"({total_prompt_tokens:,} prompt + {total_completion_tokens:,} completion)"
        )
        print(
            f"  Projected daily cost (1000 papers): "
            f"${(total_cost / len(paper_data)) * 1000:.2f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
