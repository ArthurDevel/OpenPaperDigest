"""
Test script for pymupdf4llm PDF-to-markdown conversion.

Converts a sample PDF to markdown using pymupdf4llm and saves
the output for quality comparison against Mistral OCR.

- Converts a single PDF URL to markdown
- Saves the markdown output to a file
- Reports timing and basic stats
"""

import os
import time
import urllib.request
import pymupdf4llm

# ============================================================================
# CONSTANTS
# ============================================================================

DOCUMENT_URL = "https://arxiv.org/pdf/2508.13149"
OUTPUT_MD_NAME = "output.md"

# ============================================================================
# MAIN LOGIC
# ============================================================================

script_dir = os.path.dirname(os.path.abspath(__file__))
md_path = os.path.join(script_dir, OUTPUT_MD_NAME)

# Download the PDF to a temp file (pymupdf4llm needs a file path)
pdf_path = os.path.join(script_dir, "temp.pdf")
print(f"Downloading PDF from {DOCUMENT_URL}...")
urllib.request.urlretrieve(DOCUMENT_URL, pdf_path)

# Convert PDF to markdown
print("Converting PDF to markdown...")
start_time = time.time()
text = pymupdf4llm.to_markdown(pdf_path)
elapsed = time.time() - start_time
print(f"Conversion took {elapsed:.1f}s")

# Save markdown
with open(md_path, "w", encoding="utf-8") as f:
    f.write(text)

# Clean up temp file
os.remove(pdf_path)

print(f"\nMarkdown saved to {md_path}")
print(f"Markdown length: {len(text)} characters")
print(f"Line count: {len(text.splitlines())}")
