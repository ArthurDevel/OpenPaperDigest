"""
Measures payload sizes for homepage summary API responses.

The hypothesis is that /api/papers/{uuid}/summary returns large payloads
because the server fetches the full ~2MB processed_content blob from Supabase
just to extract the five_minute_summary field.

Responsibilities:
- Fetch all 20 summaries that the homepage eagerly loads
- Measure and compare payload sizes
- Identify if fiveMinuteSummary content is the size driver or if extra data leaks through
"""

import requests
import sys
import json

# ============================================================================
# CONSTANTS
# ============================================================================

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
ITEMS_PER_PAGE = 20

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_bytes(num_bytes: int) -> str:
    """
    Formats byte count into a human-readable string.

    @param num_bytes: number of bytes
    @returns: formatted string like "1.5 KB" or "2.3 MB"
    """
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.1f} MB"


def analyze_summary_payload(data: dict) -> dict:
    """
    Breaks down the size contribution of each field in a summary response.

    @param data: parsed JSON response from /api/papers/{uuid}/summary
    @returns: dict mapping field name to its serialized size in bytes
    """
    field_sizes = {}
    for key, value in data.items():
        field_sizes[key] = len(json.dumps(value).encode("utf-8"))
    return field_sizes


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    print(f"Testing homepage summary payload sizes against: {BASE_URL}\n")

    # Step 1: Get paper UUIDs from the minimal endpoint
    minimal_url = f"{BASE_URL}/api/papers/minimal?page=1&limit={ITEMS_PER_PAGE}"
    response = requests.get(minimal_url)

    if response.status_code != 200:
        print(f"ERROR: minimal endpoint returned {response.status_code}, aborting.")
        sys.exit(1)

    papers = response.json().get("items", [])
    paper_uuids = [p["paperUuid"] for p in papers]

    minimal_size = len(response.content)
    print(f"--- Minimal list payload ---")
    print(f"  Total size: {format_bytes(minimal_size)}")
    print(f"  Papers:     {len(paper_uuids)}")
    print(f"  Per paper:  {format_bytes(minimal_size // max(len(paper_uuids), 1))}")
    print()

    # Step 2: Fetch and analyze each summary payload
    print(f"--- Summary payloads ({len(paper_uuids)} papers) ---")
    total_summary_bytes = 0
    all_field_totals: dict[str, int] = {}

    for i, uuid in enumerate(paper_uuids):
        summary_url = f"{BASE_URL}/api/papers/{uuid}/summary"
        resp = requests.get(summary_url)

        if resp.status_code != 200:
            print(f"  [{i+1:2d}] ERR {resp.status_code} | {uuid[:12]}...")
            continue

        payload_size = len(resp.content)
        total_summary_bytes += payload_size
        data = resp.json()

        # Break down by field
        field_sizes = analyze_summary_payload(data)
        for field, size in field_sizes.items():
            all_field_totals[field] = all_field_totals.get(field, 0) + size

        # Find the biggest field for this paper
        biggest_field = max(field_sizes, key=field_sizes.get)
        biggest_pct = (field_sizes[biggest_field] / payload_size * 100) if payload_size > 0 else 0

        print(f"  [{i+1:2d}] {format_bytes(payload_size):>10} | biggest field: {biggest_field} ({biggest_pct:.0f}%) | {uuid[:12]}...")

    # Step 3: Aggregate statistics
    print(f"\n--- Aggregate Summary ---")
    print(f"  Total summary data downloaded: {format_bytes(total_summary_bytes)}")
    print(f"  Average per summary:           {format_bytes(total_summary_bytes // max(len(paper_uuids), 1))}")
    print(f"  Total with minimal list:       {format_bytes(minimal_size + total_summary_bytes)}")

    print(f"\n--- Field size breakdown (summed across all {len(paper_uuids)} summaries) ---")
    sorted_fields = sorted(all_field_totals.items(), key=lambda x: x[1], reverse=True)
    for field, total_size in sorted_fields:
        pct = (total_size / total_summary_bytes * 100) if total_summary_bytes > 0 else 0
        print(f"  {field:<25} {format_bytes(total_size):>10}  ({pct:.1f}%)")

    print(f"\n  Note: The server-side query fetches the full processed_content column (~2MB)")
    print(f"  from Supabase, then extracts only fiveMinuteSummary. The transfer to the")
    print(f"  browser is smaller, but the DB-to-server transfer is the real bottleneck.")


if __name__ == "__main__":
    main()
