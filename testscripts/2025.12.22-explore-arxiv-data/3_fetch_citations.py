"""
Fetch citation data from Semantic Scholar API using arXiv ID.
"""

import httpx
import json
import time

ARXIV_ID = "2312.00752"

TIMEOUT_SECONDS = 60
DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1",
}


def fetch_semantic_scholar_data(arxiv_id: str, max_retries: int = 3) -> dict:
    """Fetch paper data including citations from Semantic Scholar."""
    # Semantic Scholar accepts arXiv IDs with ARXIV: prefix
    url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}"

    # Request ALL available fields
    all_fields = ",".join([
        # Core paper fields
        "paperId", "corpusId", "externalIds", "url", "title", "abstract",
        "venue", "publicationVenue", "year", "referenceCount", "citationCount",
        "influentialCitationCount", "isOpenAccess", "openAccessPdf",
        "fieldsOfStudy", "s2FieldsOfStudy", "publicationTypes", "publicationDate",
        "journal", "citationStyles",
        # Authors
        "authors", "authors.authorId", "authors.name", "authors.affiliations",
        # Embeddings & summaries
        "embedding", "tldr",
        # Citations with all subfields
        "citations", "citations.paperId", "citations.corpusId", "citations.externalIds",
        "citations.title", "citations.abstract", "citations.year", "citations.authors",
        "citations.venue", "citations.citationCount", "citations.influentialCitationCount",
        # References with all subfields
        "references", "references.paperId", "references.corpusId", "references.externalIds",
        "references.title", "references.abstract", "references.year", "references.authors",
        "references.venue", "references.citationCount",
    ])
    params = {
        "fields": all_fields,
        "limit": 20  # Smaller limit since we're getting more data per item
    }

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


def main():
    print(f"Fetching Semantic Scholar data for arXiv ID: {ARXIV_ID}")

    data = fetch_semantic_scholar_data(ARXIV_ID)

    with open("output/3_semantic_scholar_data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"Saved to output/3_semantic_scholar_data.json")
    print(f"\nCitation count: {data.get('citationCount', 'N/A')}")
    print(f"Reference count: {data.get('referenceCount', 'N/A')}")
    print("\nDone!")


if __name__ == "__main__":
    main()
