#!/usr/bin/env python3
"""
Verify that the PDF hashes are actually different by downloading them separately.
"""

import hashlib
import requests


def compute_pdf_hash(pdf_url: str) -> str:
    """
    Download PDF and compute its hash.

    Args:
        pdf_url: URL of the PDF

    Returns:
        str: SHA256 hash of the PDF content
    """
    print(f"Downloading: {pdf_url}")
    response = requests.get(pdf_url, timeout=30)
    response.raise_for_status()

    print(f"  Size: {len(response.content)} bytes")

    pdf_hash = hashlib.sha256(response.content).hexdigest()
    print(f"  Hash: {pdf_hash}")
    return pdf_hash


if __name__ == "__main__":
    # The three PDFs from our test results
    pdfs = [
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/07/Enter-Exit-SP26.pdf",
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/10/eurosys26-spring-final215.pdf",
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/04/niyama.pdf",
    ]

    print("=" * 80)
    print("Verifying PDF hashes")
    print("=" * 80)
    print()

    hashes = []
    for idx, pdf_url in enumerate(pdfs, 1):
        print(f"\n{idx}. {pdf_url.split('/')[-1]}")
        pdf_hash = compute_pdf_hash(pdf_url)
        hashes.append(pdf_hash)
        print()

    print("=" * 80)
    print("HASH COMPARISON:")
    print("=" * 80)

    unique_hashes = set(hashes)
    print(f"Total PDFs: {len(hashes)}")
    print(f"Unique hashes: {len(unique_hashes)}")

    if len(unique_hashes) == len(hashes):
        print("\nAll PDFs are unique!")
    else:
        print("\nWARNING: Some PDFs have the same hash!")
        for i, h in enumerate(hashes, 1):
            print(f"  PDF {i}: {h}")
