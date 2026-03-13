"""
Compare two summary generation approaches for cost analysis.

Method A (current): Mistral OCR -> markdown -> Gemini 2.5 Pro summary
Method B (proposed): PDF -> page images -> Gemini 2.5 Pro multimodal summary

- Downloads a sample PDF
- Runs both methods and saves the summaries side by side
- Reports timing and cost for each method
"""

import asyncio
import base64
import io
import os
import time
import urllib.request
import sys

import fitz  # PyMuPDF
from PIL import Image
from dotenv import load_dotenv

# Add worker directory to path so we can import project modules
worker_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'worker')
sys.path.insert(0, worker_dir)

load_dotenv(os.path.join(worker_dir, '.env'))

from shared.openrouter.client import get_llm_response

# ============================================================================
# CONSTANTS
# ============================================================================

DOCUMENT_URL = "https://arxiv.org/pdf/2508.13149"
SUMMARY_MODEL = "google/gemini-3-flash-preview"
MAX_IMAGE_WIDTH = 1080
MAX_IMAGE_HEIGHT = 1920
IMAGE_DPI = 200

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MISTRAL_OCR_OUTPUT_PATH = os.path.join(SCRIPT_DIR, 'mistral_ocr_output.md')
PROMPT_PATH = os.path.join(worker_dir, 'paperprocessor', 'prompts', 'generate_5min_summary.md')

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def download_pdf(url: str) -> bytes:
    """Download PDF from URL and return raw bytes."""
    print(f"Downloading PDF from {url}...")
    response = urllib.request.urlopen(url, timeout=30)
    return response.read()


def pdf_to_page_images(pdf_bytes: bytes) -> list[str]:
    """
    Convert all PDF pages to base64-encoded PNG images.

    @param pdf_bytes: raw PDF file bytes
    @returns list of base64-encoded PNG strings, one per page
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_images = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=IMAGE_DPI)
        img_bytes = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_bytes))

        # Downscale if needed
        width, height = image.size
        if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
            scale = min(MAX_IMAGE_WIDTH / width, MAX_IMAGE_HEIGHT / height)
            image = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.LANCZOS
            )

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        page_images.append(base64.b64encode(buf.getvalue()).decode('utf-8'))

    print(f"Converted {len(page_images)} pages to images")
    return page_images


def load_prompt() -> str:
    """Load the 5-minute summary prompt from the project prompts directory."""
    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================================
# MAIN METHODS
# ============================================================================


async def method_a_ocr_then_summary(system_prompt: str) -> dict:
    """
    Current pipeline: Mistral OCR -> markdown -> Gemini summary.
    Uses pre-existing Mistral OCR output from mistral_ocr_output.md.

    @param system_prompt: summary generation prompt
    @returns dict with summary text, timing, and cost info
    """
    print("\n--- METHOD A: Mistral OCR + Gemini summary ---")

    # Step 1: Load pre-existing Mistral OCR markdown
    with open(MISTRAL_OCR_OUTPUT_PATH, 'r', encoding='utf-8') as f:
        full_markdown = f.read()
    print(f"Loaded Mistral OCR output: {len(full_markdown)} chars")

    # Step 2: Gemini summary from markdown
    start_summary = time.time()
    result = await get_llm_response(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_markdown},
        ],
        model=SUMMARY_MODEL,
    )
    summary_time = time.time() - start_summary
    print(f"Summary generation took {summary_time:.1f}s")

    cost = result.cost_info
    print(f"Summary cost: ${cost.total_cost or 0:.4f} ({cost.prompt_tokens} prompt, {cost.completion_tokens} completion tokens)")

    return {
        "method": "A: OCR + text summary",
        "summary": result.response_text,
        "ocr_time_s": "N/A (pre-computed)",
        "summary_time_s": round(summary_time, 1),
        "total_time_s": round(summary_time, 1),
        "summary_cost_usd": cost.total_cost,
        "summary_prompt_tokens": cost.prompt_tokens,
        "summary_completion_tokens": cost.completion_tokens,
        "note": "Mistral OCR cost not included (not returned by API)",
    }


async def method_b_images_to_summary(page_images: list[str], system_prompt: str) -> dict:
    """
    Proposed pipeline: page images -> Gemini multimodal summary.

    @param page_images: list of base64-encoded PNG page images
    @param system_prompt: summary generation prompt
    @returns dict with summary text, timing, and cost info
    """
    print("\n--- METHOD B: Images directly to Gemini ---")

    # Build multimodal message with all page images
    user_content = []
    user_content.append({"type": "text", "text": "Here are all pages of the research paper as images. Please generate the summary."})
    for i, img_b64 in enumerate(page_images):
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
        })

    start_summary = time.time()
    result = await get_llm_response(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        model=SUMMARY_MODEL,
    )
    summary_time = time.time() - start_summary
    print(f"Summary generation took {summary_time:.1f}s")

    cost = result.cost_info
    print(f"Cost: ${cost.total_cost or 0:.4f} ({cost.prompt_tokens} prompt, {cost.completion_tokens} completion tokens)")

    return {
        "method": "B: Images-only multimodal summary",
        "summary": result.response_text,
        "ocr_time_s": 0,
        "summary_time_s": round(summary_time, 1),
        "total_time_s": round(summary_time, 1),
        "summary_cost_usd": cost.total_cost,
        "summary_prompt_tokens": cost.prompt_tokens,
        "summary_completion_tokens": cost.completion_tokens,
        "note": "No OCR step needed",
    }


# ============================================================================
# ENTRY POINT
# ============================================================================


async def main():
    pdf_bytes = download_pdf(DOCUMENT_URL)
    system_prompt = load_prompt()

    # Convert pages to images (used by method B, done upfront so it doesn't count against timing)
    page_images = pdf_to_page_images(pdf_bytes)

    # Run both methods
    result_a = await method_a_ocr_then_summary(system_prompt)
    result_b = await method_b_images_to_summary(page_images, system_prompt)

    # Save summaries
    with open(os.path.join(SCRIPT_DIR, "summary_method_a.md"), "w") as f:
        f.write(f"# Method A: Mistral OCR + Gemini Summary\n\n")
        f.write(result_a["summary"])

    with open(os.path.join(SCRIPT_DIR, "summary_method_b.md"), "w") as f:
        f.write(f"# Method B: Images-only Gemini Summary\n\n")
        f.write(result_b["summary"])

    # Print comparison
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)

    for r in [result_a, result_b]:
        print(f"\n{r['method']}:")
        print(f"  OCR time:       {r['ocr_time_s']}s")
        print(f"  Summary time:   {r['summary_time_s']}s")
        print(f"  Total time:     {r['total_time_s']}s")
        print(f"  Summary cost:   ${r['summary_cost_usd'] or 0:.4f}")
        print(f"  Prompt tokens:  {r['summary_prompt_tokens']}")
        print(f"  Compl. tokens:  {r['summary_completion_tokens']}")
        print(f"  Note:           {r['note']}")

    print(f"\nSummaries saved to:")
    print(f"  {os.path.join(SCRIPT_DIR, 'summary_method_a.md')}")
    print(f"  {os.path.join(SCRIPT_DIR, 'summary_method_b.md')}")


if __name__ == "__main__":
    asyncio.run(main())
