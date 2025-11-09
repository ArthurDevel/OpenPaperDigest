"""
PDF utility functions for downloading and hashing PDF files.

This module provides simple utilities to download PDFs from URLs and calculate
SHA-256 content hashes for deduplication of non-arXiv papers.
"""

import hashlib
import requests
from typing import Tuple


# ============================================================================
# CONSTANTS
# ============================================================================

DOWNLOAD_TIMEOUT_SECONDS = 30


# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

def download_pdf(url: str) -> bytes:
    """
    Download PDF from URL.

    Args:
        url: Direct URL to PDF file

    Returns:
        bytes: Raw PDF file contents

    Raises:
        ValueError: If URL is invalid or download fails
        RuntimeError: If response is not a PDF
    """
    if not url:
        raise ValueError("PDF URL cannot be empty")

    # Step 1: Download PDF
    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to download PDF from {url}: {e}")

    # Step 2: Verify content type
    content_type = response.headers.get('content-type', '').lower()
    if 'pdf' not in content_type and not url.endswith('.pdf'):
        raise RuntimeError(f"URL does not appear to be a PDF (content-type: {content_type})")

    return response.content


def calculate_pdf_hash(pdf_bytes: bytes) -> str:
    """
    Calculate SHA-256 hash of PDF content.

    Args:
        pdf_bytes: Raw PDF file contents

    Returns:
        str: Hexadecimal SHA-256 hash (64 characters)

    Raises:
        ValueError: If pdf_bytes is empty
    """
    if not pdf_bytes:
        raise ValueError("PDF bytes cannot be empty")

    return hashlib.sha256(pdf_bytes).hexdigest()


def download_and_hash_pdf(url: str) -> Tuple[bytes, str]:
    """
    Download PDF and calculate its content hash in one operation.

    Args:
        url: Direct URL to PDF file

    Returns:
        Tuple[bytes, str]: (PDF contents, SHA-256 hash)

    Raises:
        ValueError: If URL is invalid or download fails
        RuntimeError: If response is not a PDF
    """
    pdf_bytes = download_pdf(url)
    content_hash = calculate_pdf_hash(pdf_bytes)
    return pdf_bytes, content_hash
