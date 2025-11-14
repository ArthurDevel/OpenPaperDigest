#!/usr/bin/env python3
"""
Test the fixed PDF hash computation with proper headers.
"""

import requests
import hashlib


def compute_pdf_hash_fixed(pdf_url: str) -> str:
    """
    Download PDF with proper headers and compute its hash.

    Args:
        pdf_url: URL of the PDF

    Returns:
        str: SHA256 hash of the PDF content
    """
    print(f"Downloading: {pdf_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.microsoft.com/',
    }

    response = requests.get(pdf_url, timeout=30, headers=headers, allow_redirects=True)
    response.raise_for_status()

    print(f"  Content-Type: {response.headers.get('Content-Type')}")
    print(f"  Size: {len(response.content)} bytes")

    # Verify it's a PDF
    if response.content.startswith(b'%PDF'):
        print(f"  ✓ Valid PDF")
    else:
        print(f"  ✗ NOT a PDF!")
        print(f"  First 100 bytes: {response.content[:100]}")

    pdf_hash = hashlib.sha256(response.content).hexdigest()
    print(f"  Hash: {pdf_hash}")

    return pdf_hash


if __name__ == "__main__":
    # Test the three PDFs
    pdfs = [
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/07/Enter-Exit-SP26.pdf",
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/10/eurosys26-spring-final215.pdf",
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/04/niyama.pdf",
    ]

    print("=" * 80)
    print("Testing Fixed PDF Hash Computation")
    print("=" * 80)

    hashes = []
    for i, pdf_url in enumerate(pdfs, 1):
        print(f"\n{i}. {pdf_url.split('/')[-1]}")
        pdf_hash = compute_pdf_hash_fixed(pdf_url)
        hashes.append(pdf_hash)

    print(f"\n{'=' * 80}")
    print("HASH COMPARISON:")
    print(f"{'=' * 80}")
    print(f"Total PDFs: {len(hashes)}")
    print(f"Unique hashes: {len(set(hashes))}")

    if len(set(hashes)) == len(hashes):
        print("\n✓ SUCCESS! All PDFs have unique hashes!")
    else:
        print("\n✗ FAILURE! Some PDFs have duplicate hashes!")

    for i, h in enumerate(hashes, 1):
        print(f"  PDF {i}: {h}")
