"""
Test sending a PDF directly to Gemini 3 Flash via OpenRouter's `file` content type.
Compares two approaches on a large (70+ page) paper:

Method A: PDF sent as base64 via `file` content type
Method B: PDF sent as URL via `file` content type

Reports timing, cost, and token counts for each method.
"""

import asyncio
import base64
import os
import time
import urllib.request
import sys

import fitz  # PyMuPDF
from dotenv import load_dotenv

# Add worker directory to path so we can import project modules
worker_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'worker')
sys.path.insert(0, worker_dir)

load_dotenv(os.path.join(worker_dir, '.env'))

import httpx
from shared.openrouter.client import get_llm_response, BASE_URL, _HEADERS, TIMEOUT_SECONDS
from shared.openrouter.models import LLMCallResult, ApiCallCost

# ============================================================================
# CONSTANTS
# ============================================================================

# "A Survey of Large Language Models" — 144 pages, 5.6 MB
DOCUMENT_URL = "https://arxiv.org/pdf/2303.18223"
SUMMARY_MODEL = "google/gemini-3-flash-preview"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(worker_dir, 'paperprocessor', 'prompts', 'generate_5min_summary.md')

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def download_pdf(url: str) -> bytes:
    """Download PDF from URL and return raw bytes."""
    print(f"Downloading PDF from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    response = urllib.request.urlopen(req, timeout=60)
    pdf_bytes = response.read()
    print(f"Downloaded {len(pdf_bytes) / 1024 / 1024:.1f} MB")
    return pdf_bytes


def get_page_count(pdf_bytes: bytes) -> int:
    """Get the number of pages in a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count


def load_prompt() -> str:
    """Load the 5-minute summary prompt from the project prompts directory."""
    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================================
# METHODS
# ============================================================================


async def _call_openrouter_with_file(messages: list, model: str) -> dict:
    """Call OpenRouter with file content type + native PDF engine (no mistral-ocr fallback)."""
    json_payload = {
        "model": model,
        "messages": messages,
        "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}],
    }
    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, timeout=TIMEOUT_SECONDS) as client:
        response = await client.post("/chat/completions", json=json_payload)
        response.raise_for_status()
        data = response.json()

    usage = data.get("usage", {}) or {}
    choices = data.get("choices", []) or []
    first_message = choices[0].get("message") if choices else None
    response_text = (first_message or {}).get("content") if first_message else None

    return {
        "response_text": response_text,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_cost": usage.get("cost"),
    }


async def method_a_pdf_base64(pdf_bytes: bytes, system_prompt: str) -> dict:
    """PDF sent directly via OpenRouter `file` content type (base64 data URI)."""
    print("\n--- METHOD A: PDF file (base64) -> Gemini ---")

    pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
    print(f"PDF base64 size: {len(pdf_b64) / 1024 / 1024:.1f} MB")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "text", "text": "Here is the full research paper as a PDF. Please generate the summary."},
            {"type": "file", "file": {"filename": "paper.pdf", "file_data": f"data:application/pdf;base64,{pdf_b64}"}},
        ]},
    ]

    start = time.time()
    result = await _call_openrouter_with_file(messages, SUMMARY_MODEL)
    elapsed = time.time() - start

    print(f"Done in {elapsed:.1f}s — ${result['total_cost'] or 0:.4f} ({result['prompt_tokens']} prompt, {result['completion_tokens']} completion tokens)")

    return {
        "method": "A: PDF file (base64)",
        "summary": result["response_text"],
        "time_s": round(elapsed, 1),
        "cost_usd": result["total_cost"],
        "prompt_tokens": result["prompt_tokens"],
        "completion_tokens": result["completion_tokens"],
    }


async def method_b_pdf_url(pdf_url: str, system_prompt: str) -> dict:
    """PDF sent directly via OpenRouter `file` content type (URL)."""
    print("\n--- METHOD B: PDF file (URL) -> Gemini ---")
    print(f"PDF URL: {pdf_url}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "text", "text": "Here is the full research paper as a PDF. Please generate the summary."},
            {"type": "file", "file": {"filename": "paper.pdf", "file_data": pdf_url}},
        ]},
    ]

    start = time.time()
    result = await _call_openrouter_with_file(messages, SUMMARY_MODEL)
    elapsed = time.time() - start

    print(f"Done in {elapsed:.1f}s — ${result['total_cost'] or 0:.4f} ({result['prompt_tokens']} prompt, {result['completion_tokens']} completion tokens)")

    return {
        "method": "B: PDF file (URL)",
        "summary": result["response_text"],
        "time_s": round(elapsed, 1),
        "cost_usd": result["total_cost"],
        "prompt_tokens": result["prompt_tokens"],
        "completion_tokens": result["completion_tokens"],
    }


# ============================================================================
# ENTRY POINT
# ============================================================================


async def main():
    pdf_bytes = download_pdf(DOCUMENT_URL)
    page_count = get_page_count(pdf_bytes)
    print(f"Paper has {page_count} pages")

    system_prompt = load_prompt()

    results = []

    result_a = await method_a_pdf_base64(pdf_bytes, system_prompt)
    results.append(result_a)

    result_b = await method_b_pdf_url(DOCUMENT_URL, system_prompt)
    results.append(result_b)

    # Save summaries
    for r in results:
        method_letter = r["method"][0].lower()
        filename = f"summary_method_{method_letter}.md"
        with open(os.path.join(SCRIPT_DIR, filename), "w") as f:
            f.write(f"# {r['method']}\n\n")
            f.write(r["summary"] or "(no summary returned)")

    # Print comparison table
    print("\n" + "=" * 80)
    print(f"COMPARISON — {page_count}-page paper")
    print("=" * 80)
    print(f"{'Method':<30} {'Time':>8} {'Cost':>10} {'Prompt tok':>12} {'Compl tok':>12}")
    print("-" * 80)
    for r in results:
        print(f"{r['method']:<30} {r['time_s']:>7.1f}s ${r['cost_usd'] or 0:>9.4f} {r['prompt_tokens'] or 0:>12,} {r['completion_tokens'] or 0:>12,}")

    print(f"\nSummaries saved to {SCRIPT_DIR}/summary_method_[a|b].md")


if __name__ == "__main__":
    asyncio.run(main())
