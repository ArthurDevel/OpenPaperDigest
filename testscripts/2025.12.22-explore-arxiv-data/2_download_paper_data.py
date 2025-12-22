"""
Fetch raw paper data from arXiv OAI-PMH endpoint (not search API).
"""

import httpx
import json
import xmltodict

ARXIV_ID = "2312.00752"

TIMEOUT_SECONDS = 60
DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1 (+https://arxiv.org)",
}


def fetch_oai_record(arxiv_id: str) -> dict:
    """Fetch paper record from OAI-PMH endpoint."""
    # OAI-PMH GetRecord endpoint
    oai_url = f"https://export.arxiv.org/oai2?verb=GetRecord&identifier=oai:arXiv.org:{arxiv_id}&metadataPrefix=arXiv"

    with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        resp = client.get(oai_url)
        resp.raise_for_status()
        raw_xml = resp.text

    # Save raw XML
    with open("output/2_oai_raw_response.xml", "w") as f:
        f.write(raw_xml)
    print(f"Saved raw XML to output/2_oai_raw_response.xml")

    # Convert to dict
    data = xmltodict.parse(raw_xml)
    return data


def main():
    print(f"Fetching OAI-PMH record for arXiv ID: {ARXIV_ID}")

    raw_data = fetch_oai_record(ARXIV_ID)

    with open("output/2_oai_paper_data.json", "w") as f:
        json.dump(raw_data, f, indent=2, default=str)

    print(f"Saved parsed data to output/2_oai_paper_data.json")
    print("\nDone!")


if __name__ == "__main__":
    main()
