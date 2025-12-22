"""
Find the most recent papers indexed by Semantic Scholar.
Check what the indexing lag is between arXiv and S2.
"""

import httpx
import json
import time
import os
from typing import Optional

# Get script directory for output paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TIMEOUT_SECONDS = 60
DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1",
}


def fetch_with_retry(url: str, params: dict = None, max_retries: int = 3) -> Optional[dict]:
    """Fetch URL with retry on rate limit."""
    for attempt in range(max_retries):
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"  Error: {e}")
                return None
            time.sleep(1)
    return None


def search_recent_papers(query: str = "machine learning", limit: int = 20) -> list:
    """Search S2 for recent papers and return with publication dates."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "fields": "paperId,externalIds,title,publicationDate,year,venue",
        "limit": limit,
        "sort": "publicationDate:desc"  # Sort by most recent
    }

    data = fetch_with_retry(url, params)
    if not data:
        return []

    return data.get("data", [])


def check_arxiv_paper_exists(arxiv_id: str) -> Optional[dict]:
    """Check if a specific arXiv paper exists in S2."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}"
    params = {"fields": "paperId,title,publicationDate,year"}
    return fetch_with_retry(url, params)


def main():
    print("=== Finding most recent papers in Semantic Scholar index ===\n")

    # Method 1: Search for recent ML papers
    print("Method 1: Searching for recent 'machine learning' papers...")
    recent = search_recent_papers("machine learning", limit=10)

    if recent:
        print(f"\nFound {len(recent)} recent papers:\n")
        for paper in recent:
            pub_date = paper.get("publicationDate") or "Unknown"
            arxiv_id = paper.get("externalIds", {}).get("ArXiv", "N/A")
            print(f"  [{pub_date}] {paper['title'][:60]}...")
            print(f"    arXiv: {arxiv_id}")
            print()

        # Find the most recent date
        dates = [p.get("publicationDate") for p in recent if p.get("publicationDate")]
        if dates:
            print(f"Most recent publication date found: {max(dates)}")
    else:
        print("No papers found via search.")

    # Method 2: Check specific arXiv IDs from different dates
    print("\n" + "="*60)
    print("Method 2: Checking specific arXiv IDs to find indexing boundary...\n")

    # Test papers from different time periods (2512 = Dec 2025, 2511 = Nov 2025, etc.)
    test_ids = [
        # Very recent (Dec 2025)
        "2512.17908", "2512.15000", "2512.10000", "2512.05000", "2512.01000",
        # Mid December
        "2512.00500", "2512.00100",
        # Early December / Late November
        "2511.19000", "2511.15000", "2511.10000",
        # Mid November
        "2511.05000", "2511.01000",
        # October
        "2510.10000", "2510.01000",
    ]

    found_papers = []
    not_found = []

    for arxiv_id in test_ids:
        time.sleep(0.3)
        result = check_arxiv_paper_exists(arxiv_id)
        if result:
            found_papers.append({
                "arxiv_id": arxiv_id,
                "title": result.get("title", "")[:50],
                "publicationDate": result.get("publicationDate"),
            })
            print(f"  ✓ {arxiv_id} - FOUND ({result.get('publicationDate', 'no date')})")
        else:
            not_found.append(arxiv_id)
            print(f"  ✗ {arxiv_id} - NOT FOUND")

    print(f"\n\nSummary:")
    print(f"  Found: {len(found_papers)} papers")
    print(f"  Not found: {len(not_found)} papers")

    if found_papers:
        # Find the most recent indexed arXiv paper
        most_recent = max(found_papers, key=lambda x: x["arxiv_id"])
        print(f"\n  Most recent indexed arXiv ID: {most_recent['arxiv_id']}")
        print(f"  Title: {most_recent['title']}...")

    # Save results
    output_path = os.path.join(SCRIPT_DIR, "output/6_indexing_status.json")
    with open(output_path, "w") as f:
        json.dump({
            "recent_search_results": recent,
            "arxiv_checks": {
                "found": found_papers,
                "not_found": not_found,
            }
        }, f, indent=2)

    print(f"\nSaved results to output/6_indexing_status.json")


if __name__ == "__main__":
    main()
