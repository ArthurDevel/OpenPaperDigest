"""Fetch citation edges from the Semantic Scholar API.

Connects to the production database to get papers with S2 IDs, then uses the
S2 batch API to fetch reference edges for each paper. Outputs:
- output/citation_edges.json  (source -> target edge list)
- output/paper_index.json     (s2_paper_id -> {arxiv_id, title} for our papers)

Responsibilities:
- Query DB for papers with populated s2_ids
- Batch-fetch references from S2 API (500 papers per call)
- Build citation edge list with retry/backoff for rate limiting
- Save results with metadata
"""
import json
import os
import time
from datetime import datetime, timezone

import psycopg2
import requests
from dotenv import load_dotenv


# ============================================================================
# CONSTANTS
# ============================================================================

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_BATCH_SIZE = 500
# Match production S2 client retry strategy: burst fast, back off on 429
MAX_RETRIES = 5
RETRY_BASE_DELAY = 0.1  # seconds, doubles each retry

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main() -> None:
    """Main entrypoint: fetch papers from DB, query S2 API, save edges."""
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set in environment or .env file")

    s2_api_key = os.environ.get("S2_API_KEY", "").strip() or None

    # Step 1: Get papers from DB
    papers = fetch_papers_from_db(database_url)
    print(f"Found {len(papers)} papers with S2 IDs in the database")

    if not papers:
        print("No papers to process. Exiting.")
        return

    # Step 2: Build paper index
    paper_index = {}
    s2_ids = []
    for arxiv_id, s2_paper_id, title in papers:
        paper_index[s2_paper_id] = {
            "arxiv_id": arxiv_id,
            "title": title,
        }
        s2_ids.append(s2_paper_id)

    # Step 3: Fetch references in batches
    all_edges = []
    batches = [s2_ids[i:i + S2_BATCH_SIZE] for i in range(0, len(s2_ids), S2_BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        print(f"Batch {batch_idx + 1}/{len(batches)}: fetching references for {len(batch)} papers...")
        batch_edges = fetch_references_batch(batch, s2_api_key)
        all_edges.extend(batch_edges)
        print(f"  -> {len(batch_edges)} edges from this batch, {len(all_edges)} edges total")

    # Step 4: Save results
    save_citation_edges(all_edges, len(papers))
    save_paper_index(paper_index)

    print(f"\nDone. {len(all_edges)} citation edges saved to output/citation_edges.json")
    print(f"Paper index ({len(paper_index)} papers) saved to output/paper_index.json")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_papers_from_db(database_url: str) -> list[tuple[str, str, str]]:
    """Query the DB for all papers that have s2_ids populated.

    @param database_url: PostgreSQL connection string
    @returns List of (arxiv_id, s2_paper_id, title) tuples
    """
    query = """
        SELECT
            arxiv_id,
            s2_ids->>'s2_paper_id' AS s2_paper_id,
            title
        FROM papers
        WHERE s2_ids IS NOT NULL
          AND s2_ids != '{}'::jsonb
          AND s2_ids->>'s2_paper_id' IS NOT NULL
          AND s2_ids->>'s2_paper_id' != ''
    """
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [(row[0], row[1], row[2]) for row in rows]


def fetch_references_batch(s2_paper_ids: list[str], api_key: str | None) -> list[dict]:
    """Fetch references for a batch of papers using the S2 batch API.

    @param s2_paper_ids: List of S2 paper IDs (max 500)
    @param api_key: Optional S2 API key for higher rate limits
    @returns List of edge dicts {"source": ..., "target": ...}
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    params = {"fields": "references.paperId"}
    body = {"ids": s2_paper_ids}

    response_data = request_with_retry(
        url=S2_BATCH_URL,
        headers=headers,
        params=params,
        json_body=body,
    )

    edges = []
    null_count = 0
    no_refs_count = 0
    with_refs_count = 0

    for entry in response_data:
        if entry is None:
            null_count += 1
            continue

        source_id = entry.get("paperId")
        references = entry.get("references") or []

        if len(references) == 0:
            no_refs_count += 1
        else:
            with_refs_count += 1

        for ref in references:
            if ref is None:
                continue
            target_id = ref.get("paperId")
            if target_id:
                edges.append({"source": source_id, "target": target_id})

    print(f"  -> Breakdown: {with_refs_count} with refs, {no_refs_count} no refs, {null_count} null (not in S2)")
    return edges


def request_with_retry(
    url: str,
    headers: dict,
    params: dict,
    json_body: dict,
) -> list:
    """POST request with exponential backoff on 429 responses.
    Matches the production S2 client strategy: burst fast, back off on rate limit.

    @param url: Request URL
    @param headers: Request headers
    @param params: Query parameters
    @param json_body: JSON request body
    @returns Parsed JSON response (list)
    """
    delay = RETRY_BASE_DELAY

    for attempt in range(MAX_RETRIES):
        response = requests.post(url, headers=headers, params=params, json=json_body, timeout=120)

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            print(f"  Rate limited (429). Retrying in {delay:.1f}s... (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(delay)
            delay *= 2
            continue

        # Non-retryable error
        raise RuntimeError(
            f"S2 API request failed: status={response.status_code}, "
            f"body={response.text[:500]}"
        )

    # Final attempt, let it raise on any error
    response = requests.post(url, headers=headers, params=params, json=json_body, timeout=120)
    if response.status_code == 200:
        return response.json()
    raise RuntimeError(f"Max retries exceeded. Last status={response.status_code}")


def save_citation_edges(edges: list[dict], total_papers: int) -> None:
    """Save citation edges to output/citation_edges.json.

    @param edges: List of {"source": ..., "target": ...} dicts
    @param total_papers: Number of papers queried
    """
    output = {
        "metadata": {
            "total_papers_queried": total_papers,
            "total_edges": len(edges),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "edges": edges,
    }

    path = os.path.join(OUTPUT_DIR, "citation_edges.json")
    with open(path, "w") as f:
        json.dump(output, f, indent=2)


def save_paper_index(paper_index: dict) -> None:
    """Save paper index mapping to output/paper_index.json.

    @param paper_index: Dict mapping s2_paper_id -> {arxiv_id, title}
    """
    path = os.path.join(OUTPUT_DIR, "paper_index.json")
    with open(path, "w") as f:
        json.dump(paper_index, f, indent=2)


if __name__ == "__main__":
    main()
