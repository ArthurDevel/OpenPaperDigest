"""
Measures API response times for the homepage loading flow.

Reproduces what the browser does on homepage load:
- 1x GET /api/papers/minimal?page=1&limit=20
- 20x GET /api/papers/{uuid}/summary (fired eagerly for every card)

Responsibilities:
- Measure response time for the minimal papers list endpoint
- Measure response time for each individual summary endpoint
- Report total wall-clock time for the full homepage data load
"""

import time
import requests
import sys
import statistics

# ============================================================================
# CONSTANTS
# ============================================================================

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
ITEMS_PER_PAGE = 20

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def measure_request(url: str) -> dict:
    """
    Fires a GET request and returns timing + status info.

    @param url: the full URL to request
    @returns: dict with url, status_code, elapsed_ms, content_length_bytes
    """
    start = time.perf_counter()
    response = requests.get(url)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "url": url,
        "status_code": response.status_code,
        "elapsed_ms": round(elapsed_ms, 1),
        "content_length_bytes": len(response.content),
    }


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    print(f"Testing homepage API response times against: {BASE_URL}\n")

    # Step 1: Fetch the minimal papers list (first thing the homepage does)
    minimal_url = f"{BASE_URL}/api/papers/minimal?page=1&limit={ITEMS_PER_PAGE}"
    print(f"--- Fetching minimal papers list ---")
    minimal_result = measure_request(minimal_url)
    print(f"  Status: {minimal_result['status_code']}")
    print(f"  Time:   {minimal_result['elapsed_ms']} ms")
    print(f"  Size:   {minimal_result['content_length_bytes']} bytes")

    if minimal_result["status_code"] != 200:
        print(f"\nERROR: minimal endpoint returned {minimal_result['status_code']}, aborting.")
        sys.exit(1)

    # Parse paper UUIDs from response
    response = requests.get(minimal_url)
    papers = response.json().get("items", [])
    paper_uuids = [p["paperUuid"] for p in papers]
    print(f"\n  Got {len(paper_uuids)} papers\n")

    # Step 2: Fetch summaries for each paper (homepage does this eagerly for all 20)
    print(f"--- Fetching {len(paper_uuids)} summaries (simulating eager pre-fetch) ---")
    summary_results = []

    for i, uuid in enumerate(paper_uuids):
        summary_url = f"{BASE_URL}/api/papers/{uuid}/summary"
        result = measure_request(summary_url)
        summary_results.append(result)
        status_icon = "OK" if result["status_code"] == 200 else f"ERR {result['status_code']}"
        print(f"  [{i+1:2d}/{len(paper_uuids)}] {result['elapsed_ms']:>8.1f} ms | {result['content_length_bytes']:>8} bytes | {status_icon} | {uuid[:12]}...")

    # Step 3: Report summary statistics
    times = [r["elapsed_ms"] for r in summary_results]
    total_summary_time_sequential = sum(times)

    print(f"\n--- Summary Statistics ---")
    print(f"  Minimal list endpoint:     {minimal_result['elapsed_ms']:>8.1f} ms")
    print(f"  Summary endpoints (sequential):")
    print(f"    Min:                     {min(times):>8.1f} ms")
    print(f"    Max:                     {max(times):>8.1f} ms")
    print(f"    Median:                  {statistics.median(times):>8.1f} ms")
    print(f"    Mean:                    {statistics.mean(times):>8.1f} ms")
    print(f"    Total (sequential):      {total_summary_time_sequential:>8.1f} ms")
    print(f"")
    print(f"  Total data load time:")
    print(f"    Sequential (worst case): {minimal_result['elapsed_ms'] + total_summary_time_sequential:>8.1f} ms")
    print(f"    Parallel (best case):    {minimal_result['elapsed_ms'] + max(times):>8.1f} ms")
    print(f"")
    print(f"  Note: Browser fires all {len(paper_uuids)} summary requests in parallel,")
    print(f"  but they still compete for server resources and DB connections.")


if __name__ == "__main__":
    main()
