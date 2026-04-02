"""Fetch references for external nodes to expand the citation graph one layer out.

Loads the existing citation graph, identifies external nodes (papers referenced
by our papers but not in our DB), and fetches THEIR references from the S2 API.
This gives the graph more edges so PageRank can flow through external papers
instead of them being dead-end sinks.

Outputs:
- output/citation_edges_expanded.json  (merged edges: original + new)

Reuses the retry/backoff strategy from fetch_citation_edges.py.
"""
import json
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv


# ============================================================================
# CONSTANTS
# ============================================================================

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_BATCH_SIZE = 500
MAX_RETRIES = 5
RETRY_BASE_DELAY = 0.1  # seconds, doubles each retry

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
PROGRESS_FILE = os.path.join(OUTPUT_DIR, "external_fetch_progress.json")


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main() -> None:
    """Fetch references for external nodes and merge with existing edges."""
    load_dotenv()
    s2_api_key = os.environ.get("S2_API_KEY", "").strip() or None

    # Step 1: Load existing data
    edges_data = load_json(os.path.join(OUTPUT_DIR, "citation_edges.json"))
    paper_index = load_json(os.path.join(OUTPUT_DIR, "paper_index.json"))

    existing_edges = edges_data["edges"]
    our_s2_ids = set(paper_index.keys())

    print(f"Loaded {len(existing_edges)} existing edges")
    print(f"Our papers: {len(our_s2_ids)}")

    # Step 2: Find all nodes in the graph
    all_nodes = set()
    for edge in existing_edges:
        all_nodes.add(edge["source"])
        all_nodes.add(edge["target"])

    # Step 3: Identify external nodes (not in our DB)
    external_nodes = all_nodes - our_s2_ids
    print(f"Total nodes in graph: {len(all_nodes)}")
    print(f"External nodes to fetch: {len(external_nodes)}")

    # Step 4: Check for progress (resume support)
    already_fetched = set()
    new_edges = []
    if os.path.exists(PROGRESS_FILE):
        progress = load_json(PROGRESS_FILE)
        already_fetched = set(progress.get("fetched_ids", []))
        new_edges = progress.get("new_edges", [])
        print(f"Resuming: {len(already_fetched)} already fetched, {len(new_edges)} new edges so far")

    remaining = [nid for nid in external_nodes if nid not in already_fetched]
    print(f"Remaining to fetch: {len(remaining)}")

    if not remaining:
        print("Nothing to fetch. Merging and saving...")
        save_merged_edges(existing_edges, new_edges, len(our_s2_ids), len(external_nodes))
        return

    # Step 5: Fetch references in batches
    batches = [remaining[i:i + S2_BATCH_SIZE] for i in range(0, len(remaining), S2_BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        print(f"\nBatch {batch_idx + 1}/{len(batches)}: fetching references for {len(batch)} external papers...")
        batch_edges = fetch_references_batch(batch, s2_api_key)
        new_edges.extend(batch_edges)
        already_fetched.update(batch)
        print(f"  -> {len(batch_edges)} new edges, {len(new_edges)} total new edges")

        # Save progress every 5 batches
        if (batch_idx + 1) % 5 == 0:
            save_progress(list(already_fetched), new_edges)
            print(f"  -> Progress saved ({len(already_fetched)}/{len(external_nodes)} fetched)")

    # Step 6: Save final progress
    save_progress(list(already_fetched), new_edges)

    # Step 7: Merge and save
    save_merged_edges(existing_edges, new_edges, len(our_s2_ids), len(external_nodes))

    print(f"\nDone. {len(new_edges)} new edges from external references.")
    print(f"Total edges: {len(existing_edges) + len(new_edges)}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_json(path: str) -> dict:
    """Load and parse a JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def fetch_references_batch(s2_paper_ids: list[str], api_key: str | None) -> list[dict]:
    """Fetch references for a batch of papers using the S2 batch API."""
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
    """POST request with exponential backoff on 429 and timeout errors."""
    delay = RETRY_BASE_DELAY

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, headers=headers, params=params, json=json_body, timeout=120)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            print(f"  Request error: {type(e).__name__}. Retrying in {delay:.1f}s... (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(delay)
            delay *= 2
            continue

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            print(f"  Rate limited (429). Retrying in {delay:.1f}s... (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(delay)
            delay *= 2
            continue

        raise RuntimeError(
            f"S2 API request failed: status={response.status_code}, "
            f"body={response.text[:500]}"
        )

    # Final attempt
    response = requests.post(url, headers=headers, params=params, json=json_body, timeout=120)
    if response.status_code == 200:
        return response.json()
    raise RuntimeError(f"Max retries exceeded. Last status={response.status_code}")


def save_progress(fetched_ids: list[str], new_edges: list[dict]) -> None:
    """Save progress to disk for resume support."""
    progress = {
        "fetched_ids": fetched_ids,
        "new_edges": new_edges,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)


def save_merged_edges(
    existing_edges: list[dict],
    new_edges: list[dict],
    our_paper_count: int,
    external_node_count: int,
) -> None:
    """Merge original and new edges, deduplicate, and save."""
    # Deduplicate edges
    edge_set = set()
    merged = []
    for edge in existing_edges + new_edges:
        key = (edge["source"], edge["target"])
        if key not in edge_set:
            edge_set.add(key)
            merged.append(edge)

    output = {
        "metadata": {
            "total_papers_queried": our_paper_count,
            "external_nodes_fetched": external_node_count,
            "total_edges": len(merged),
            "original_edges": len(existing_edges),
            "new_edges_from_external": len(new_edges),
            "deduplicated_edges": len(merged),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "edges": merged,
    }

    path = os.path.join(OUTPUT_DIR, "citation_edges_expanded.json")
    with open(path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nMerged edges saved to {path}")
    print(f"  Original: {len(existing_edges)}")
    print(f"  New: {len(new_edges)}")
    print(f"  After dedup: {len(merged)}")


if __name__ == "__main__":
    main()
