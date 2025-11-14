#!/usr/bin/env python3
"""
Debug script to see what's actually being downloaded when we request PDFs.
"""

import requests
import hashlib


def debug_pdf_download(pdf_url: str):
    """
    Download PDF and show detailed information about the response.

    Args:
        pdf_url: URL of the PDF
    """
    print(f"\nDownloading: {pdf_url}")
    print(f"URL filename: {pdf_url.split('/')[-1]}")

    response = requests.get(pdf_url, timeout=30, allow_redirects=True)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"Content-Length: {response.headers.get('Content-Length')}")
    print(f"Size downloaded: {len(response.content)} bytes")
    print(f"Final URL: {response.url}")

    # Check if redirected
    if response.history:
        print(f"\nRedirects:")
        for i, resp in enumerate(response.history):
            print(f"  {i+1}. {resp.status_code} -> {resp.url}")

    # Check first bytes to see if it's actually a PDF
    first_bytes = response.content[:100]
    print(f"\nFirst 100 bytes: {first_bytes[:100]}")

    # Check if it starts with PDF header
    if first_bytes.startswith(b'%PDF'):
        print("✓ Valid PDF header")
    else:
        print("✗ NOT a valid PDF! Might be HTML error page")

    # Compute hash
    pdf_hash = hashlib.sha256(response.content).hexdigest()
    print(f"\nSHA256 Hash: {pdf_hash}")

    # Save to file for inspection
    filename = f"debug_{pdf_url.split('/')[-1]}"
    with open(filename, 'wb') as f:
        f.write(response.content)
    print(f"Saved to: {filename}")

    return pdf_hash


if __name__ == "__main__":
    # Test the three PDFs
    pdfs = [
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/07/Enter-Exit-SP26.pdf",
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/10/eurosys26-spring-final215.pdf",
        "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/04/niyama.pdf",
    ]

    print("=" * 80)
    print("PDF Download Debug")
    print("=" * 80)

    hashes = []
    for i, pdf_url in enumerate(pdfs, 1):
        print(f"\n{'=' * 80}")
        print(f"PDF #{i}")
        print(f"{'=' * 80}")
        pdf_hash = debug_pdf_download(pdf_url)
        hashes.append(pdf_hash)

    print(f"\n{'=' * 80}")
    print("HASH COMPARISON:")
    print(f"{'=' * 80}")
    print(f"Total PDFs: {len(hashes)}")
    print(f"Unique hashes: {len(set(hashes))}")

    for i, h in enumerate(hashes, 1):
        print(f"  PDF {i}: {h}")
