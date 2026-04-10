"""
Theme detection for weekly research papers using LLM-based classification.

Reads papers_by_week.json (from step 01) and processes each week sequentially,
using an LLM to assign papers to themes.

Responsibilities:
- Bootstrap themes from the first week's papers (15-30 themes)
- Incrementally assign papers to existing themes for subsequent weeks
- Batch large weeks (>80 papers) into chunks of ~60
- Track theme registry, weekly assignments, and LLM cost
- Output theme_assignments.json with all results
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

INPUT_FILE = SCRIPT_DIR / "output" / "papers_by_week.json"
OUTPUT_FILE = SCRIPT_DIR / "output" / "theme_assignments.json"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash"

BATCH_SIZE = 60
BATCH_THRESHOLD = 60

# Cost per token (rough estimate for gemini-2.5-flash-preview via OpenRouter)
COST_PER_INPUT_TOKEN = 0.15 / 1_000_000
COST_PER_OUTPUT_TOKEN = 0.60 / 1_000_000


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment or .env file")

    papers_by_week = load_papers()
    weeks_sorted = sorted(papers_by_week.keys())

    print(f"Loaded {len(weeks_sorted)} weeks: {weeks_sorted}")

    theme_registry: dict[str, dict] = {}  # name -> {description, first_seen_week}
    weekly_assignments: dict[str, list] = {}  # week -> [{arxiv_id, title, themes}]
    total_tokens = 0
    total_cost = 0.0

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, week in enumerate(weeks_sorted):
            papers = papers_by_week[week]
            print(f"\n--- Week {week} ({len(papers)} papers) [{i+1}/{len(weeks_sorted)}] ---")

            is_bootstrap = (i == 0)
            week_assignments, new_themes, tokens, cost = await process_week(
                client, papers, theme_registry, week, is_bootstrap
            )

            # Update theme registry with new themes
            for theme_name, theme_desc in new_themes.items():
                if theme_name not in theme_registry:
                    theme_registry[theme_name] = {
                        "description": theme_desc,
                        "first_seen_week": week,
                    }

            weekly_assignments[week] = week_assignments
            total_tokens += tokens
            total_cost += cost

            print(f"  Assigned {len(week_assignments)} papers, "
                  f"{len(new_themes)} new themes, "
                  f"cost: ${cost:.4f}")

    save_output(theme_registry, weekly_assignments, total_tokens, total_cost)

    print(f"\n=== DONE ===")
    print(f"Total themes: {len(theme_registry)}")
    print(f"Total assignments: {sum(len(a) for a in weekly_assignments.values())}")
    print(f"Total tokens: {total_tokens}")
    print(f"Total cost: ${total_cost:.4f}")


# ============================================================================
# MAIN LOGIC
# ============================================================================

async def process_week(
    client: httpx.AsyncClient,
    papers: list[dict],
    theme_registry: dict[str, dict],
    week: str,
    is_bootstrap: bool,
) -> tuple[list[dict], dict[str, str], int, float]:
    """
    Process all papers for a single week. Batches if needed.

    Args:
        client: httpx async client
        papers: list of paper dicts with arxiv_id, title, abstract
        theme_registry: current theme registry (name -> {description, first_seen_week})
        week: the week string (e.g. "2026-03-12")
        is_bootstrap: True for the first week

    Returns:
        (assignments, new_themes, tokens_used, cost)
        - assignments: list of {arxiv_id, title, themes}
        - new_themes: dict of theme_name -> description (newly created this week)
        - tokens_used: int
        - cost: float
    """
    batches = create_batches(papers)
    all_assignments: list[dict] = []
    all_new_themes: dict[str, str] = {}
    total_tokens = 0
    total_cost = 0.0

    for batch_idx, batch in enumerate(batches):
        print(f"  Batch {batch_idx + 1}/{len(batches)} ({len(batch)} papers)")

        # For batch N>1, include previous batch assignments for consistency
        prev_assignments = all_assignments if batch_idx > 0 else None

        assignments, new_themes, tokens, cost = await call_llm_for_batch(
            client, batch, theme_registry, all_new_themes,
            week, is_bootstrap, prev_assignments
        )

        all_assignments.extend(assignments)
        all_new_themes.update(new_themes)
        total_tokens += tokens
        total_cost += cost

    return all_assignments, all_new_themes, total_tokens, total_cost


async def call_llm_for_batch(
    client: httpx.AsyncClient,
    papers: list[dict],
    theme_registry: dict[str, dict],
    week_new_themes: dict[str, str],
    week: str,
    is_bootstrap: bool,
    prev_assignments: list[dict] | None,
) -> tuple[list[dict], dict[str, str], int, float]:
    """
    Call the LLM for a single batch of papers.
    Retries once on failure, then skips the batch with a warning.

    Args:
        papers: batch of paper dicts
        theme_registry: current theme registry
        week_new_themes: new themes already created this week (from earlier batches)
        week: the week string
        is_bootstrap: True for the first week
        prev_assignments: assignments from previous batch (for consistency), or None

    Returns:
        (assignments, new_themes, tokens_used, cost)
    """
    prompt = build_prompt(papers, theme_registry, week_new_themes, is_bootstrap, prev_assignments)

    for attempt in range(2):
        try:
            response = await send_llm_request(client, prompt)
            result = parse_llm_response(response, papers, is_bootstrap)

            tokens = response.get("usage", {})
            input_tokens = tokens.get("prompt_tokens", 0)
            output_tokens = tokens.get("completion_tokens", 0)
            total_tokens = input_tokens + output_tokens
            cost = (input_tokens * COST_PER_INPUT_TOKEN) + (output_tokens * COST_PER_OUTPUT_TOKEN)

            return result["assignments"], result["new_themes"], total_tokens, cost

        except Exception as e:
            if attempt == 0:
                print(f"    WARNING: LLM call failed (attempt 1): {e}. Retrying...")
                await asyncio.sleep(2)
            else:
                print(f"    WARNING: LLM call failed (attempt 2): {e}. Skipping batch.")
                # Return empty results for this batch
                return [], {}, 0, 0.0

    return [], {}, 0, 0.0  # unreachable, but satisfies type checker


async def send_llm_request(client: httpx.AsyncClient, prompt: str) -> dict:
    """
    Send a request to OpenRouter and return the parsed response JSON.

    Args:
        prompt: the user prompt to send

    Returns:
        The full API response as a dict
    """
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a research paper classification assistant. "
                    "You assign papers to research themes. "
                    "Always respond with valid JSON matching the requested schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
    if resp.status_code != 200:
        print(f"    API error {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"OpenRouter API error: {data['error']}")

    return data


# ============================================================================
# PROMPT BUILDING
# ============================================================================

def build_prompt(
    papers: list[dict],
    theme_registry: dict[str, dict],
    week_new_themes: dict[str, str],
    is_bootstrap: bool,
    prev_assignments: list[dict] | None,
) -> str:
    """
    Build the LLM prompt based on whether this is bootstrap or incremental.

    Args:
        papers: batch of paper dicts
        theme_registry: existing theme registry
        week_new_themes: new themes from earlier batches this week
        is_bootstrap: True for the first week
        prev_assignments: assignments from previous batch, or None

    Returns:
        The prompt string
    """
    papers_text = format_papers_for_prompt(papers)

    if is_bootstrap:
        return build_bootstrap_prompt(papers_text, prev_assignments)
    else:
        return build_incremental_prompt(papers_text, theme_registry, week_new_themes, prev_assignments)


def build_bootstrap_prompt(papers_text: str, prev_assignments: list[dict] | None) -> str:
    prev_context = ""
    if prev_assignments:
        prev_context = (
            "\n\nFor consistency, here are the theme assignments from the previous batch "
            "in this same week. Use the same theme names where applicable:\n"
            + json.dumps(prev_assignments, indent=2)
        )

    return f"""Given these research papers, create 15-30 specific research themes. Each theme should be more specific than a field (not 'NLP') but broader than a single paper. Assign each paper to 1-2 themes.
{prev_context}

Papers:
{papers_text}

Respond with JSON in this exact format:
{{
  "themes": [
    {{"name": "Theme Name", "description": "Brief description of what this theme covers"}}
  ],
  "assignments": [
    {{"arxiv_id": "2603.12345", "themes": ["Theme Name 1", "Theme Name 2"]}}
  ]
}}

Every paper must be assigned to at least one theme. Theme names should be concise but descriptive."""


def build_incremental_prompt(
    papers_text: str,
    theme_registry: dict[str, dict],
    week_new_themes: dict[str, str],
    prev_assignments: list[dict] | None,
) -> str:
    # Combine existing registry themes with any new themes from earlier batches
    all_themes = []
    for name, info in theme_registry.items():
        all_themes.append(f"- {name}: {info['description']}")
    for name, desc in week_new_themes.items():
        if name not in theme_registry:
            all_themes.append(f"- {name}: {desc}")
    themes_text = "\n".join(all_themes)

    prev_context = ""
    if prev_assignments:
        prev_context = (
            "\n\nFor consistency, here are the theme assignments from the previous batch "
            "in this same week:\n"
            + json.dumps(prev_assignments, indent=2)
        )

    return f"""Here are the current research themes:
{themes_text}

Assign each paper below to 1-2 existing themes. If a paper truly doesn't fit any existing theme, propose a new theme with name and description. Do NOT rename existing themes.
{prev_context}

Papers:
{papers_text}

Respond with JSON in this exact format:
{{
  "new_themes": [
    {{"name": "New Theme Name", "description": "Brief description"}}
  ],
  "assignments": [
    {{"arxiv_id": "2603.12345", "themes": ["Existing Theme", "New Theme If Any"]}}
  ]
}}

If no new themes are needed, return an empty list for new_themes.
Every paper must be assigned to at least one theme."""


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_papers() -> dict[str, list[dict]]:
    """Load papers_by_week.json and return {week_start: [papers]} dict."""
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    with open(INPUT_FILE) as f:
        raw = json.load(f)

    # Step 01 outputs {"weeks": [{week_start, papers, ...}], ...}
    result = {}
    for week_obj in raw["weeks"]:
        result[week_obj["week_start"]] = week_obj["papers"]
    return result


def save_output(
    theme_registry: dict[str, dict],
    weekly_assignments: dict[str, list],
    total_tokens: int,
    total_cost: float,
) -> None:
    """Save results to output/theme_assignments.json."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "themes": theme_registry,
        "weekly_assignments": weekly_assignments,
        "llm_cost": {"total_tokens": total_tokens, "total_cost": total_cost},
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved output to {OUTPUT_FILE}")


def format_papers_for_prompt(papers: list[dict]) -> str:
    """Format a list of papers into a readable string for the LLM prompt."""
    lines = []
    for p in papers:
        arxiv_id = p.get("arxiv_id", "unknown")
        title = p.get("title", "No title")
        abstract = p.get("abstract") or "No abstract"
        # Truncate long abstracts to keep prompt size reasonable
        if len(abstract) > 500:
            abstract = abstract[:500] + "..."
        lines.append(f"[{arxiv_id}] {title}\nAbstract: {abstract}\n")
    return "\n".join(lines)


def create_batches(papers: list[dict]) -> list[list[dict]]:
    """
    Split papers into batches if the count exceeds BATCH_THRESHOLD.

    Args:
        papers: all papers for a week

    Returns:
        List of batches (each batch is a list of paper dicts)
    """
    if len(papers) <= BATCH_THRESHOLD:
        return [papers]

    batches = []
    for i in range(0, len(papers), BATCH_SIZE):
        batches.append(papers[i : i + BATCH_SIZE])
    return batches


def parse_llm_response(
    response: dict,
    papers: list[dict],
    is_bootstrap: bool,
) -> dict:
    """
    Parse the LLM response and extract assignments and new themes.

    Args:
        response: full API response dict
        papers: the papers that were sent in this batch
        is_bootstrap: True for the first week

    Returns:
        {"assignments": [...], "new_themes": {name: description}}
    """
    content = response["choices"][0]["message"]["content"]
    data = json.loads(content)

    new_themes: dict[str, str] = {}

    if is_bootstrap:
        # Extract themes from bootstrap response
        for theme in data.get("themes", []):
            new_themes[theme["name"]] = theme["description"]
    else:
        # Extract only newly proposed themes
        for theme in data.get("new_themes", []):
            new_themes[theme["name"]] = theme["description"]

    # Build a lookup of paper titles by arxiv_id
    title_by_id = {p.get("arxiv_id", ""): p.get("title", "") for p in papers}

    assignments = []
    for a in data.get("assignments", []):
        arxiv_id = a.get("arxiv_id", "")
        themes = a.get("themes", [])
        assignments.append({
            "arxiv_id": arxiv_id,
            "title": title_by_id.get(arxiv_id, ""),
            "themes": themes,
        })

    return {"assignments": assignments, "new_themes": new_themes}


if __name__ == "__main__":
    asyncio.run(main())
