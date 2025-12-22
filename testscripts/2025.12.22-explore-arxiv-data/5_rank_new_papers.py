"""
Fetch arXiv papers from a specific date, rank by author credibility:
- Average h-index of authors
- Average citations per paper of authors

Note: Semantic Scholar has a ~5 day indexing lag, so we query papers from
5 days ago to ensure they're indexed.
"""

import httpx
import json
import time
import os
import xmltodict
from datetime import datetime, timedelta
from typing import Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

# Get script directory for output paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Days to look back (to ensure papers are indexed in Semantic Scholar)
DAYS_BACK = 5

# Categories to filter on. Set to None or [] to get ALL papers for the day.
# Examples:
#   CATEGORIES = ["cs.LG"]                    # Machine Learning only
#   CATEGORIES = ["cs.LG", "cs.AI", "cs.CV"]  # ML, AI, and Computer Vision
#   CATEGORIES = ["cs.*"]                     # All Computer Science (wildcard)
#   CATEGORIES = None                         # ALL papers across all categories
CATEGORIES: list[str] | None = ["cs.*"]

# Maximum papers to fetch (None = fetch all)
MAX_PAPERS: int | None = None

# API settings
TIMEOUT_SECONDS = 60
PAGE_SIZE = 500  # arXiv API allows up to 2000 per request

# Semantic Scholar rate limiting: incremental backoff on failure (1s, 2s, 3s, 4s, 5s)
S2_BACKOFF_SEQUENCE = [1, 2, 3, 4, 5]  # Seconds to wait on each consecutive failure

DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1",
}

# =============================================================================
# RUNTIME STATE (don't modify)
# =============================================================================

author_cache: dict = {}
start_time: float = 0


def fetch_with_retry(url: str, params: dict = None) -> Optional[dict]:
    """Fetch URL with incremental backoff on failure.

    On 429 or error: wait 1s, 2s, 3s, 4s, 5s (then stay at 5s).
    On success: reset backoff and return.
    Never gives up.
    """
    backoff_idx = 0

    while True:
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
                resp = client.get(url, params=params)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 404:
                    return None

                if resp.status_code == 429:
                    wait = S2_BACKOFF_SEQUENCE[min(backoff_idx, len(S2_BACKOFF_SEQUENCE) - 1)]
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    backoff_idx += 1
                    continue

                resp.raise_for_status()

        except Exception as e:
            wait = S2_BACKOFF_SEQUENCE[min(backoff_idx, len(S2_BACKOFF_SEQUENCE) - 1)]
            print(f"  Error: {e}, waiting {wait}s...")
            time.sleep(wait)
            backoff_idx += 1


def fetch_arxiv_papers_by_date(
    categories: list[str] | None = None,
    target_date: datetime | None = None,
    max_papers: int | None = None
) -> list:
    """Fetch ALL papers from arXiv API for a specific date using pagination.

    Args:
        categories: List of arXiv categories to filter on (e.g., ["cs.LG", "cs.AI"]).
                   Set to None or [] to get all papers.
        target_date: Date to fetch papers for. Defaults to DAYS_BACK days ago.
        max_papers: Maximum number of papers to fetch. None = fetch all.

    arXiv API limits: max 2000 per request, paginate with 'start' parameter.
    Response includes opensearch:totalResults for total count.
    """
    if target_date is None:
        target_date = datetime.now() - timedelta(days=DAYS_BACK)

    date_str = target_date.strftime("%Y%m%d")
    date_start = f"{date_str}0000"
    date_end = f"{date_str}2359"

    # Build search query
    date_query = f"submittedDate:[{date_start} TO {date_end}]"

    if categories:
        # Multiple categories: OR them together
        if len(categories) == 1:
            cat_query = f"cat:{categories[0]}"
        else:
            cat_query = "(" + " OR ".join(f"cat:{cat}" for cat in categories) + ")"
        search_query = f"{cat_query} AND {date_query}"
        cat_display = ", ".join(categories)
    else:
        search_query = date_query
        cat_display = "ALL"

    api_url = "https://export.arxiv.org/api/query"

    print(f"Fetching papers from {target_date.strftime('%Y-%m-%d')}...")
    print(f"Categories: {cat_display}")
    print(f"Query: {search_query}")

    all_papers = []
    start = 0
    total_results = None

    with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        while True:
            params = {
                "search_query": search_query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": start,
                "max_results": PAGE_SIZE,
            }

            resp = client.get(api_url, params=params)
            resp.raise_for_status()
            raw_xml = resp.text

            data = xmltodict.parse(raw_xml)

            # Get total results on first request
            if total_results is None:
                total_results = int(data["feed"].get("opensearch:totalResults", 0))
                print(f"Total papers available: {total_results}")

                # Save first page raw response
                raw_output_path = os.path.join(SCRIPT_DIR, "output/5_arxiv_daily_raw.xml")
                with open(raw_output_path, "w") as f:
                    f.write(raw_xml)

            # Extract papers from this page
            try:
                entries = data["feed"].get("entry", [])
                if not entries:
                    break
                if isinstance(entries, dict):
                    entries = [entries]

                for entry in entries:
                    # Extract arXiv ID from the id URL
                    id_url = entry.get("id", "")
                    arxiv_id = id_url.split("/abs/")[-1] if "/abs/" in id_url else None

                    # Remove version suffix for cleaner ID
                    if arxiv_id and "v" in arxiv_id:
                        arxiv_id = arxiv_id.rsplit("v", 1)[0]

                    # Get authors
                    authors = entry.get("author", [])
                    if isinstance(authors, dict):
                        authors = [authors]
                    author_names = [a.get("name", "") for a in authors]

                    all_papers.append({
                        "arxiv_id": arxiv_id,
                        "title": entry.get("title", "").replace("\n", " ").strip(),
                        "authors": author_names,
                        "published": entry.get("published"),
                        "categories": entry.get("arxiv:primary_category", {}).get("@term", ""),
                        "abstract": (entry.get("summary", "") or "")[:200] + "...",
                    })

                print(f"  Fetched {len(all_papers)}/{total_results} papers...")

            except KeyError as e:
                print(f"Error parsing page: {e}")
                break

            # Check if we hit max_papers limit or have all papers
            if max_papers and len(all_papers) >= max_papers:
                all_papers = all_papers[:max_papers]
                break
            if len(all_papers) >= total_results:
                break

            # Next page
            start += PAGE_SIZE
            time.sleep(0.5)  # arXiv API rate limit

    print(f"Fetched {len(all_papers)} papers total")
    return all_papers


def get_author_stats(author_id: str) -> Optional[dict]:
    """Get author stats from Semantic Scholar, with caching."""
    if author_id in author_cache:
        return author_cache[author_id]

    url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}"
    params = {"fields": "authorId,name,paperCount,citationCount,hIndex"}

    data = fetch_with_retry(url, params)
    if data:
        paper_count = data.get("paperCount", 0)
        citation_count = data.get("citationCount", 0)
        data["avgCitationsPerPaper"] = citation_count / paper_count if paper_count > 0 else 0
        author_cache[author_id] = data

    return data


def get_paper_author_ids(arxiv_id: str) -> list:
    """Get author IDs for a paper from Semantic Scholar."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}"
    params = {"fields": "authors,authors.authorId,authors.name"}

    data = fetch_with_retry(url, params)
    if not data:
        return []

    return data.get("authors", [])


def compute_paper_score(arxiv_id: str) -> dict:
    """Compute author-based score for a paper."""
    authors = get_paper_author_ids(arxiv_id)

    if not authors:
        return {
            "num_authors": 0,
            "avg_h_index": 0,
            "avg_citations_per_paper": 0,
            "authors_found": 0,
        }

    h_indices = []
    avg_citations = []

    for author in authors:
        author_id = author.get("authorId")
        if not author_id:
            continue

        stats = get_author_stats(author_id)

        if stats:
            h_index = stats.get("hIndex")
            avg_cit = stats.get("avgCitationsPerPaper", 0)

            if h_index is not None:
                h_indices.append(h_index)
            if avg_cit:
                avg_citations.append(avg_cit)

    num_authors = len(authors)

    return {
        "num_authors": num_authors,
        "avg_h_index": sum(h_indices) / len(h_indices) if h_indices else 0,
        "avg_citations_per_paper": sum(avg_citations) / len(avg_citations) if avg_citations else 0,
        "authors_found": len(h_indices),
        "total_h_index": sum(h_indices),
        "h_indices": h_indices,
    }


def elapsed_time() -> str:
    """Return elapsed time since start."""
    elapsed = time.time() - start_time
    return f"{elapsed:.1f}s"


def main():
    global start_time
    start_time = time.time()

    target_date = datetime.now() - timedelta(days=DAYS_BACK)
    cat_display = ", ".join(CATEGORIES) if CATEGORIES else "ALL"

    print(f"=== Ranking arXiv papers by author credibility ===")
    print(f"Categories: {cat_display}")
    print(f"Target date: {target_date.strftime('%Y-%m-%d')} ({DAYS_BACK} days ago)\n")

    # Step 1: Fetch ALL papers from arXiv for target date (with pagination)
    papers = fetch_arxiv_papers_by_date(
        categories=CATEGORIES,
        target_date=target_date,
        max_papers=MAX_PAPERS
    )

    if not papers:
        print("No papers found. Try a different date.")
        return

    print(f"\n[{elapsed_time()}] Total papers to process: {len(papers)}\n")

    # Step 2: Score each paper
    scored_papers = []
    for i, paper in enumerate(papers):
        arxiv_id = paper.get("arxiv_id")
        if not arxiv_id:
            continue

        # Progress update every 5 papers or first/last
        if i == 0 or (i + 1) % 5 == 0 or i == len(papers) - 1:
            print(f"[{elapsed_time()}] Processing {i+1}/{len(papers)}: {arxiv_id}")

        score = compute_paper_score(arxiv_id)

        paper["score"] = score
        scored_papers.append(paper)

        # Brief stats every 5 papers
        if (i + 1) % 5 == 0:
            print(f"  -> Avg h-index: {score['avg_h_index']:.1f}, Authors found: {score['authors_found']}/{score['num_authors']}")

    # Step 3: Rank by average h-index
    print("\n\n=== TOP 10 BY AVERAGE H-INDEX ===\n")
    by_h_index = sorted(scored_papers, key=lambda p: p["score"]["avg_h_index"], reverse=True)[:10]

    for i, paper in enumerate(by_h_index, 1):
        score = paper["score"]
        print(f"{i}. [{paper['arxiv_id']}] (avg h-index: {score['avg_h_index']:.1f})")
        print(f"   {paper['title'][:80]}")
        print(f"   Authors: {score['num_authors']}, Found: {score['authors_found']}")
        print()

    # Step 4: Rank by average citations per paper
    print("\n=== TOP 10 BY AVERAGE CITATIONS PER PAPER ===\n")
    by_citations = sorted(scored_papers, key=lambda p: p["score"]["avg_citations_per_paper"], reverse=True)[:10]

    for i, paper in enumerate(by_citations, 1):
        score = paper["score"]
        print(f"{i}. [{paper['arxiv_id']}] (avg cit/paper: {score['avg_citations_per_paper']:.1f})")
        print(f"   {paper['title'][:80]}")
        print(f"   Authors: {score['num_authors']}, Found: {score['authors_found']}")
        print()

    # Save full results
    output_path = os.path.join(SCRIPT_DIR, "output/5_ranked_papers.json")
    with open(output_path, "w") as f:
        json.dump({
            "categories": CATEGORIES,
            "target_date": target_date.strftime("%Y-%m-%d"),
            "total_papers": len(scored_papers),
            "top_by_h_index": by_h_index[:10],
            "top_by_citations": by_citations[:10],
            "all_papers": scored_papers,
        }, f, indent=2)

    print(f"\n[{elapsed_time()}] Done! Saved results to output/5_ranked_papers.json")


if __name__ == "__main__":
    main()


# =============================================================================
# USAGE EXAMPLES
# =============================================================================
#
# To change categories, modify the CATEGORIES constant at the top of the file:
#
#   CATEGORIES = ["cs.LG"]                    # Machine Learning only (default)
#   CATEGORIES = ["cs.LG", "cs.AI"]           # ML and AI
#   CATEGORIES = ["cs.LG", "cs.AI", "cs.CV"]  # ML, AI, and Computer Vision
#   CATEGORIES = ["stat.ML"]                  # Statistics - Machine Learning
#   CATEGORIES = None                         # ALL papers (all categories)
#
# Common CS categories:
#   cs.LG  - Machine Learning
#   cs.AI  - Artificial Intelligence
#   cs.CV  - Computer Vision
#   cs.CL  - Computation and Language (NLP)
#   cs.NE  - Neural and Evolutionary Computing
#   cs.RO  - Robotics
#
# To limit papers for testing:
#   MAX_PAPERS = 20  # Only process first 20 papers
#
# To change how far back to look:
#   DAYS_BACK = 7    # Look at papers from 7 days ago
#
