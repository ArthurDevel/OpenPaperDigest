"""
Batch Embedding Script for SPECTER2

Re-embeds all papers in arxiv_papers using SPECTER2 base model via HuggingFace API.
This ensures query embeddings and paper embeddings are in the same embedding space.

Usage:
    python 2_batch_embed_specter2.py
    python 2_batch_embed_specter2.py --dry-run
    python 2_batch_embed_specter2.py --limit 100
"""

import os
import json
import argparse
import asyncio
import time
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from huggingface_hub import AsyncInferenceClient


# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))


# =============================================================================
# CONFIGURATION
# =============================================================================

MYSQL_HOST = "localhost"
MYSQL_PORT = "3306"
MYSQL_USER = os.getenv("MYSQL_USER", "workflow_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "workflow_db")

HF_TOKEN = os.getenv("HF_TOKEN")

SPECTER2_MODEL = "allenai/specter2_base"
EMBEDDING_MODEL_NAME = "specter2_base"

# BERT has 512 token limit; scientific text tokenizes densely (~3.5 chars/token)
MAX_TEXT_CHARS = 1500

# Rate limiting: HuggingFace allows 200 requests/minute = 3.33/sec
REQUESTS_PER_SECOND = 3.0
CONCURRENT_REQUESTS = 100

# Database batch size
DB_BATCH_SIZE = 50


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def get_database_url() -> str:
    return f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"


def load_papers_to_embed() -> list[dict]:
    engine = create_engine(get_database_url())
    query = text("SELECT arxiv_id, title, abstract FROM arxiv_papers WHERE title IS NOT NULL")

    with engine.connect() as conn:
        result = conn.execute(query)
        return [dict(row._mapping) for row in result]


def update_embeddings_batch(engine, updates: list[tuple[str, list[float]]]) -> int:
    if not updates:
        return 0

    query = text("""
        UPDATE arxiv_papers
        SET embedding_vector = :embedding, embedding_model = :model_name, updated_at = NOW()
        WHERE arxiv_id = :arxiv_id
    """)

    try:
        with engine.connect() as conn:
            for arxiv_id, embedding in updates:
                conn.execute(query, {
                    "arxiv_id": arxiv_id,
                    "embedding": json.dumps(embedding),
                    "model_name": EMBEDDING_MODEL_NAME,
                })
            conn.commit()
        return len(updates)
    except Exception as e:
        print(f"\n[DB ERROR] {e}")
        return 0


# =============================================================================
# EMBEDDING
# =============================================================================

def format_paper_text(title: str, abstract: Optional[str]) -> str:
    text = f"{title} [SEP] {abstract}" if abstract else title
    return text[:MAX_TEXT_CHARS] if len(text) > MAX_TEXT_CHARS else text


async def embed_paper(
    client: AsyncInferenceClient,
    semaphore: asyncio.Semaphore,
    paper: dict,
) -> tuple[str, Optional[list[float]]]:
    arxiv_id = paper["arxiv_id"]
    text = format_paper_text(paper["title"], paper["abstract"])

    async with semaphore:
        try:
            result = await client.feature_extraction(text, model=SPECTER2_MODEL)

            if hasattr(result, 'tolist'):
                result = result.tolist()

            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], list):
                    return (arxiv_id, result[0])
                return (arxiv_id, result)

            return (arxiv_id, None)
        except Exception as e:
            print(f"\n[ERROR] {arxiv_id}: {e}")
            return (arxiv_id, None)


async def process_papers(papers: list[dict], dry_run: bool = False) -> tuple[int, int]:
    client = AsyncInferenceClient(provider="hf-inference", api_key=HF_TOKEN)
    engine = create_engine(get_database_url())
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    success_count = 0
    error_count = 0
    pending_updates: list[tuple[str, list[float]]] = []
    total = len(papers)
    start_time = time.time()

    # Create all tasks - semaphore controls concurrency
    tasks = [embed_paper(client, semaphore, paper) for paper in papers]
    processed = 0

    for coro in asyncio.as_completed(tasks):
        arxiv_id, embedding = await coro
        processed += 1

        if embedding is not None:
            success_count += 1
            if not dry_run:
                pending_updates.append((arxiv_id, embedding))
                if len(pending_updates) >= DB_BATCH_SIZE:
                    update_embeddings_batch(engine, pending_updates)
                    pending_updates = []
        else:
            error_count += 1

        # Progress every 50
        if processed % 50 == 0 or processed == total:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total - processed) / rate if rate > 0 else 0
            print(f"[{processed}/{total}] Rate: {rate:.1f}/s | ETA: {eta:.0f}s | Success: {success_count} | Errors: {error_count}")


    # Flush remaining
    if pending_updates and not dry_run:
        written = update_embeddings_batch(engine, pending_updates)
        success_count += written

    return success_count, error_count


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Re-embed papers using SPECTER2 (async)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not HF_TOKEN:
        print("Error: HF_TOKEN not set")
        return

    print("=" * 80)
    print("SPECTER2 Batch Embedding (Async)")
    print(f"Model: {SPECTER2_MODEL}")
    print(f"Rate: {REQUESTS_PER_SECOND} req/s | Concurrent: {CONCURRENT_REQUESTS}")
    print("=" * 80)

    papers = load_papers_to_embed()
    print(f"Found {len(papers)} papers")

    if args.limit:
        papers = papers[:args.limit]
        print(f"Limited to {len(papers)}")

    if not papers:
        return

    print(f"ETA: {len(papers)/REQUESTS_PER_SECOND/60:.1f} min\n")

    start = time.time()
    success, errors = asyncio.run(process_papers(papers, args.dry_run))
    elapsed = time.time() - start

    print(f"\n{'='*80}")
    print(f"DONE: {success} success, {errors} errors in {elapsed:.0f}s ({len(papers)/elapsed:.1f}/s)")
    if args.dry_run:
        print("(dry run)")


if __name__ == "__main__":
    main()
