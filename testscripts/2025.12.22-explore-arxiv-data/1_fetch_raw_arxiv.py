"""
Fetch raw data from arXiv API and save it to see exactly what we get back.
"""

import httpx
import json
import xmltodict

# Example paper ID - a recent ML paper
ARXIV_ID = "2312.00752"

ARXIV_EXPORT_HOST = "https://export.arxiv.org"
TIMEOUT_SECONDS = 60
DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1 (+https://arxiv.org)",
}


def fetch_raw_metadata(arxiv_id: str) -> dict:
    """Fetch raw metadata from arXiv API and return as dict."""
    query_url = f"{ARXIV_EXPORT_HOST}/api/query?id_list={arxiv_id}"

    with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        resp = client.get(query_url)
        resp.raise_for_status()
        raw_xml = resp.text

    # Save raw XML
    with open("output/1_raw_response.xml", "w") as f:
        f.write(raw_xml)
    print(f"Saved raw XML to output/1_raw_response.xml")

    # Convert XML to dict for easier viewing
    data = xmltodict.parse(raw_xml)

    return data


def main():
    print(f"Fetching metadata for arXiv ID: {ARXIV_ID}")

    raw_data = fetch_raw_metadata(ARXIV_ID)

    # Save as JSON for easy inspection
    with open("output/1_raw_metadata.json", "w") as f:
        json.dump(raw_data, f, indent=2, default=str)

    print(f"Saved parsed metadata to output/1_raw_metadata.json")
    print("\nDone! Check the output folder for the raw data.")


if __name__ == "__main__":
    main()
