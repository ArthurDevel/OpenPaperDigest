"""
For a given arXiv paper, fetch author statistics:
- Number of papers per author
- Total citations per author
- Average citations per paper
"""

import httpx
import json
import time

ARXIV_ID = "2312.00752"

TIMEOUT_SECONDS = 60
DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1",
}


def fetch_with_retry(url: str, params: dict, max_retries: int = 3) -> dict:
    """Fetch URL with retry on rate limit."""
    for attempt in range(max_retries):
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
    raise Exception("Max retries exceeded")


def fetch_paper_authors(arxiv_id: str) -> list:
    """Get author IDs from a paper."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}"
    params = {"fields": "authors,authors.authorId,authors.name"}
    data = fetch_with_retry(url, params)
    return data.get("authors", [])


def fetch_author_details(author_id: str) -> dict:
    """Fetch all available author data."""
    url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}"
    # Request ALL available author fields
    params = {
        "fields": ",".join([
            "authorId", "name", "url", "affiliations", "homepage",
            "paperCount", "citationCount", "hIndex", "externalIds",
            # Also get their papers with key fields
            "papers", "papers.paperId", "papers.title", "papers.year",
            "papers.citationCount", "papers.venue", "papers.externalIds"
        ])
    }
    return fetch_with_retry(url, params)


def main():
    print(f"Fetching author stats for arXiv paper: {ARXIV_ID}\n")

    # Step 1: Get authors from paper
    authors = fetch_paper_authors(ARXIV_ID)
    print(f"Found {len(authors)} authors\n")

    # Step 2: Fetch details for each author
    author_data = []
    for author in authors:
        author_id = author.get("authorId")
        if not author_id:
            continue

        print(f"Fetching stats for {author['name']}...")
        time.sleep(0.5)  # Be nice to the API

        details = fetch_author_details(author_id)

        # Add computed field
        paper_count = details.get("paperCount", 0)
        citation_count = details.get("citationCount", 0)
        avg_citations = citation_count / paper_count if paper_count > 0 else 0
        details["avgCitationsPerPaper"] = round(avg_citations, 2)

        author_data.append(details)

        # Print summary
        print(f"  Papers: {paper_count}")
        print(f"  Citations: {citation_count}")
        print(f"  Avg citations/paper: {avg_citations:.2f}")
        print(f"  h-index: {details.get('hIndex')}")
        print()

    # Save full raw results
    with open("output/4_author_stats.json", "w") as f:
        json.dump(author_data, f, indent=2)

    print(f"Saved to output/4_author_stats.json")


if __name__ == "__main__":
    main()
