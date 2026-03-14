"""
Compare arXiv API metadata (title, authors) vs LLM-extracted metadata from page images.

For 5 arxiv papers, this script:
1. Fetches title + authors from the arXiv Atom API (free, instant)
2. Downloads the PDF, renders the first 3 pages as images
3. Sends those images to Gemini 2.5 Pro (current pipeline model) to extract title + authors
4. Prints a side-by-side comparison

Goal: determine if the LLM metadata extraction step can be skipped for arXiv papers,
since title/authors are already available from the arXiv API.

Requirements: pip install httpx fitz pymupdf python-dotenv Pillow
"""

import asyncio
import base64
import io
import json
import os
import time
import urllib.request
import xml.etree.ElementTree as ET

import fitz  # PyMuPDF
import httpx
from dotenv import load_dotenv

# Load .env from worker directory for OPENROUTER_API_KEY
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKER_DIR = os.path.join(SCRIPT_DIR, "..", "..", "worker")
load_dotenv(os.path.join(WORKER_DIR, ".env"))

# ============================================================================
# CONSTANTS
# ============================================================================

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in environment")

OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = "google/gemini-2.5-pro"
TIMEOUT_SECONDS = 120
MAX_PAGES_FOR_METADATA = 3

# 5 papers with varying title/author complexity
TEST_PAPERS = [
    "2303.18223",   # A Survey of Large Language Models (many authors)
    "1706.03762",   # Attention Is All You Need (8 authors)
    "2005.14165",   # Language Models are Few-Shot Learners (GPT-3, many authors)
    "2301.07041",   # LLaMA: Open and Efficient Foundation Language Models (short author list)
    "2310.06825",   # Mistral 7B (few authors, accent in name)
]

ARXIV_API_BASE = "http://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}

METADATA_SYSTEM_PROMPT = """# Extract Document Metadata

You are a document analysis expert. Your task is to extract the title and authors from academic paper pages.

## Instructions

1. Analyze the provided document pages (typically the first 3 pages)
2. Identify the main title of the paper (not section headers or subtitles)
3. Identify all authors listed (usually on the title page or first page)
4. Return the information in the requested JSON format

## Output Format

```json
{
  "title": "The main title of the paper",
  "authors": "Author 1, Author 2, Author 3"
}
```

## Guidelines

- **Title**: Extract the main document title, usually prominently displayed on the first page
- **Authors**: Extract all author names, comma-separated, in the order they appear
- **Focus**: Look primarily at the first page where title and authors typically appear
- **Format**: Keep original capitalization and spelling
- **Missing data**: If title or authors cannot be determined, return null for that field
- **Exclude**: Do not include section titles, headers, or institutional affiliations as the main title"""


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_arxiv_metadata(arxiv_id: str) -> dict:
    """Fetch title and authors from the arXiv Atom API.

    Args:
        arxiv_id: arXiv paper identifier (e.g. "2303.18223")

    Returns:
        Dict with "title" and "authors" keys.
    """
    url = f"{ARXIV_API_BASE}?id_list={arxiv_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml_text = resp.read().decode("utf-8")

    root = ET.fromstring(xml_text)
    entry = root.find("atom:entry", ARXIV_NS)
    if entry is None:
        raise RuntimeError(f"No entry found for {arxiv_id}")

    title_el = entry.find("atom:title", ARXIV_NS)
    title = title_el.text.strip().replace("\n", " ") if title_el is not None else None

    authors = []
    for author_el in entry.findall("atom:author", ARXIV_NS):
        name_el = author_el.find("atom:name", ARXIV_NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    return {
        "title": title,
        "authors": ", ".join(authors),
    }


def download_pdf(arxiv_id: str) -> bytes:
    """Download PDF from arXiv.

    Args:
        arxiv_id: arXiv paper identifier

    Returns:
        Raw PDF bytes.
    """
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def pdf_to_page_images(pdf_bytes: bytes, max_pages: int = MAX_PAGES_FOR_METADATA) -> list[str]:
    """Render first N pages of a PDF as base64-encoded PNG strings.

    Args:
        pdf_bytes: Raw PDF file bytes.
        max_pages: Maximum number of pages to render.

    Returns:
        List of base64-encoded PNG strings (one per page).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page_num in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        images.append(base64.b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return images


async def extract_metadata_via_llm(page_images_b64: list[str]) -> dict:
    """Send page images to the LLM and extract title + authors.

    Args:
        page_images_b64: List of base64-encoded PNG page images.

    Returns:
        Dict with "title" and "authors" from the LLM response.
    """
    user_content = [
        {"type": "text", "text": "Extract the title and authors from these document pages:"}
    ]
    for img_b64 in page_images_b64:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
        })

    messages = [
        {"role": "system", "content": METADATA_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(base_url=OPENROUTER_BASE_URL, headers=headers, timeout=TIMEOUT_SECONDS) as client:
        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)

    cost = data.get("usage", {}).get("cost", "unknown")
    return {
        "title": parsed.get("title"),
        "authors": parsed.get("authors"),
        "cost": cost,
    }


def normalize(text: str | None) -> str:
    """Lowercase and collapse whitespace for fuzzy comparison."""
    if not text:
        return ""
    return " ".join(text.lower().split())


def titles_match(a: str | None, b: str | None) -> bool:
    """Check if two titles are essentially the same (case/whitespace insensitive)."""
    return normalize(a) == normalize(b)


def count_author_overlap(arxiv_authors: str | None, llm_authors: str | None) -> tuple[int, int, int]:
    """Count how many authors overlap between the two sources.

    Returns:
        Tuple of (matching, arxiv_count, llm_count).
    """
    if not arxiv_authors or not llm_authors:
        return (0, 0, 0)

    # Split by comma, normalize each name
    arxiv_names = {normalize(n) for n in arxiv_authors.split(",") if n.strip()}
    llm_names = {normalize(n) for n in llm_authors.split(",") if n.strip()}

    matching = len(arxiv_names & llm_names)
    return (matching, len(arxiv_names), len(llm_names))


# ============================================================================
# MAIN
# ============================================================================

async def compare_one_paper(arxiv_id: str) -> dict:
    """Run full comparison for a single paper.

    Args:
        arxiv_id: arXiv paper identifier.

    Returns:
        Dict with comparison results.
    """
    print(f"\n{'='*70}")
    print(f"Paper: {arxiv_id}")
    print(f"{'='*70}")

    # Step 1: arXiv API metadata
    print("  Fetching arXiv API metadata...")
    arxiv_start = time.time()
    arxiv_meta = fetch_arxiv_metadata(arxiv_id)
    arxiv_time = time.time() - arxiv_start
    print(f"  arXiv API: {arxiv_time:.2f}s")
    print(f"    Title:   {arxiv_meta['title'][:80]}...")
    print(f"    Authors: {arxiv_meta['authors'][:80]}...")

    # Step 2: Download PDF and render pages
    print("  Downloading PDF...")
    pdf_bytes = download_pdf(arxiv_id)
    print(f"  PDF size: {len(pdf_bytes)/1024/1024:.1f} MB")

    print("  Rendering first 3 pages...")
    page_images = pdf_to_page_images(pdf_bytes)
    print(f"  Rendered {len(page_images)} pages")

    # Step 3: LLM extraction
    print(f"  Sending to {LLM_MODEL}...")
    llm_start = time.time()
    llm_meta = await extract_metadata_via_llm(page_images)
    llm_time = time.time() - llm_start
    print(f"  LLM extraction: {llm_time:.2f}s, cost: ${llm_meta['cost']}")
    print(f"    Title:   {(llm_meta['title'] or 'None')[:80]}...")
    print(f"    Authors: {(llm_meta['authors'] or 'None')[:80]}...")

    # Step 4: Compare
    title_ok = titles_match(arxiv_meta["title"], llm_meta["title"])
    matching, arxiv_count, llm_count = count_author_overlap(arxiv_meta["authors"], llm_meta["authors"])

    print(f"\n  COMPARISON:")
    print(f"    Title match:   {'YES' if title_ok else 'NO'}")
    print(f"    Authors:       {matching}/{arxiv_count} arXiv authors found in LLM output ({llm_count} total from LLM)")
    print(f"    arXiv time:    {arxiv_time:.2f}s (free)")
    print(f"    LLM time:      {llm_time:.2f}s (${llm_meta['cost']})")

    if not title_ok:
        print(f"    TITLE DIFF:")
        print(f"      arXiv: {arxiv_meta['title']}")
        print(f"      LLM:   {llm_meta['title']}")

    return {
        "arxiv_id": arxiv_id,
        "arxiv_title": arxiv_meta["title"],
        "llm_title": llm_meta["title"],
        "title_match": title_ok,
        "arxiv_authors": arxiv_meta["authors"],
        "llm_authors": llm_meta["authors"],
        "author_overlap": matching,
        "arxiv_author_count": arxiv_count,
        "llm_author_count": llm_count,
        "arxiv_time_s": arxiv_time,
        "llm_time_s": llm_time,
        "llm_cost": llm_meta["cost"],
    }


def write_results_markdown(results: list[dict]) -> None:
    """Write a detailed side-by-side comparison to results.md.

    Args:
        results: List of comparison result dicts from compare_one_paper.
    """
    output_path = os.path.join(SCRIPT_DIR, "results.md")
    lines = []
    lines.append("# arXiv API vs LLM Metadata Extraction Comparison")
    lines.append("")
    lines.append(f"Model: `{LLM_MODEL}` | Pages sent: {MAX_PAGES_FOR_METADATA}")
    lines.append("")

    for r in results:
        lines.append(f"---")
        lines.append(f"## {r['arxiv_id']}")
        lines.append("")

        # Title comparison
        lines.append("### Title")
        lines.append("")
        lines.append(f"**arXiv API:**")
        lines.append(f"> {r['arxiv_title']}")
        lines.append("")
        lines.append(f"**LLM extracted:**")
        lines.append(f"> {r['llm_title']}")
        lines.append("")
        lines.append(f"Match: **{'YES' if r['title_match'] else 'NO'}**")
        lines.append("")

        # Authors comparison
        lines.append("### Authors")
        lines.append("")
        lines.append(f"**arXiv API** ({r['arxiv_author_count']} authors):")
        lines.append(f"> {r['arxiv_authors']}")
        lines.append("")
        lines.append(f"**LLM extracted** ({r['llm_author_count']} authors):")
        lines.append(f"> {r['llm_authors']}")
        lines.append("")
        lines.append(f"Overlap: **{r['author_overlap']}/{r['arxiv_author_count']}** arXiv authors found in LLM output")
        lines.append("")

        # Timing
        lines.append("### Timing and Cost")
        lines.append("")
        lines.append(f"- arXiv API: {r['arxiv_time_s']:.2f}s (free)")
        cost_str = f"${r['llm_cost']:.5f}" if isinstance(r["llm_cost"], (int, float)) else str(r["llm_cost"])
        lines.append(f"- LLM: {r['llm_time_s']:.2f}s ({cost_str})")
        lines.append("")

    # Summary table
    lines.append("---")
    lines.append("## Summary")
    lines.append("")
    lines.append("| arXiv ID | Title Match | Author Overlap | arXiv Time | LLM Time | LLM Cost |")
    lines.append("|----------|------------|----------------|------------|----------|----------|")

    total_llm_cost = 0
    total_llm_time = 0
    titles_matched = 0

    for r in results:
        author_str = f"{r['author_overlap']}/{r['arxiv_author_count']}"
        cost_str = f"${r['llm_cost']:.5f}" if isinstance(r["llm_cost"], (int, float)) else str(r["llm_cost"])
        if isinstance(r["llm_cost"], (int, float)):
            total_llm_cost += r["llm_cost"]
        total_llm_time += r["llm_time_s"]
        if r["title_match"]:
            titles_matched += 1
        lines.append(f"| {r['arxiv_id']} | {'YES' if r['title_match'] else 'NO'} | {author_str} | {r['arxiv_time_s']:.2f}s | {r['llm_time_s']:.2f}s | {cost_str} |")

    lines.append("")
    lines.append(f"**Titles matched:** {titles_matched}/{len(results)}")
    lines.append(f"**Total LLM time:** {total_llm_time:.1f}s")
    lines.append(f"**Total LLM cost:** ${total_llm_cost:.4f}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nResults written to {output_path}")


async def main():
    """Run comparison for all test papers, print summary, and write results.md."""
    results = []
    for arxiv_id in TEST_PAPERS:
        result = await compare_one_paper(arxiv_id)
        results.append(result)
        # Small delay to avoid rate limiting
        await asyncio.sleep(1)

    # Summary table to stdout
    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'arXiv ID':<14} {'Title?':<8} {'Authors':<16} {'arXiv (s)':<10} {'LLM (s)':<10} {'LLM Cost':<10}")
    print("-" * 70)

    total_llm_cost = 0
    total_llm_time = 0
    titles_matched = 0

    for r in results:
        author_str = f"{r['author_overlap']}/{r['arxiv_author_count']}"
        cost_str = f"${r['llm_cost']}" if isinstance(r["llm_cost"], (int, float)) else str(r["llm_cost"])
        if isinstance(r["llm_cost"], (int, float)):
            total_llm_cost += r["llm_cost"]
        total_llm_time += r["llm_time_s"]
        if r["title_match"]:
            titles_matched += 1

        print(f"{r['arxiv_id']:<14} {'YES' if r['title_match'] else 'NO':<8} {author_str:<16} {r['arxiv_time_s']:<10.2f} {r['llm_time_s']:<10.2f} {cost_str:<10}")

    print("-" * 70)
    print(f"Titles matched: {titles_matched}/{len(results)}")
    print(f"Total LLM time: {total_llm_time:.1f}s")
    print(f"Total LLM cost: ${total_llm_cost:.4f}")

    # Write detailed results to markdown
    write_results_markdown(results)


if __name__ == "__main__":
    asyncio.run(main())
