"""
Autoresearch optimization loop for theme detection prompts.

Iteratively mutates the theme detection prompt, re-runs theme detection on all
papers, and scores the result using an embedding discrimination metric. Keeps
improvements and reverts failures.

Responsibilities:
- Manage a prompt mutation loop (default 5 iterations, override via ITERATIONS env var)
- Call LLM (gemini-2.5-flash via OpenRouter) to mutate prompts and detect themes
- Score theme groupings using S = mean_intra / mean_inter on precomputed embeddings
- Log iteration results and save the best prompt to disk
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv

# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

PAPERS_FILE = SCRIPT_DIR.parent / "2026.04.09-research-frontiers-detection" / "output" / "papers_by_week.json"
EMBEDDINGS_FILE = SCRIPT_DIR / "output" / "embeddings.json"
OUTPUT_FILE = SCRIPT_DIR / "output" / "loop_results.json"
BEST_PROMPT_FILE = SCRIPT_DIR / "output" / "best_prompt.txt"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash"

NUM_ITERATIONS = int(os.environ.get("ITERATIONS", "5"))
BATCH_SIZE = 80

COST_PER_INPUT_TOKEN = 0.15 / 1_000_000
COST_PER_OUTPUT_TOKEN = 0.60 / 1_000_000

BASELINE_PROMPT = (
    "Given these research papers, create 15-30 specific research themes. "
    "Each theme should be more specific than a field (not 'NLP') but broader "
    "than a single paper. Assign each paper to 1-2 themes. Theme names should "
    "be concise but descriptive."
)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment or .env file")

    papers = load_all_papers()
    embeddings = load_embeddings()
    print(f"Loaded {len(papers)} papers, {len(embeddings)} embeddings")

    # Only keep papers that have embeddings
    papers = [p for p in papers if p["arxiv_id"] in embeddings]
    print(f"Papers with embeddings: {len(papers)}")

    batches = create_batches(papers)
    print(f"Batches: {len(batches)} (size ~{BATCH_SIZE})")

    current_prompt = BASELINE_PROMPT
    best_prompt = BASELINE_PROMPT
    best_score = None
    baseline_score = None

    iterations_log = []
    total_cost = 0.0
    total_tokens = 0

    async with httpx.AsyncClient(timeout=180.0) as client:
        # Run baseline (iteration 0)
        print(f"\nIteration 0/{NUM_ITERATIONS}: running baseline theme detection ({len(batches)} batches)...")
        assignments, tokens, cost = await run_theme_detection(client, papers, batches, current_prompt)
        total_cost += cost
        total_tokens += tokens

        score, mean_intra, mean_inter, num_themes = compute_score(assignments, embeddings)
        baseline_score = score
        best_score = score
        print(f"Iteration 0/{NUM_ITERATIONS}: scoring... S={score:.4f} (intra={mean_intra:.4f}, inter={mean_inter:.4f}, {num_themes} themes)")

        iterations_log.append({
            "iteration": 0,
            "prompt_summary": current_prompt[:200],
            "mutation": "baseline",
            "score": score,
            "mean_intra": mean_intra,
            "mean_inter": mean_inter,
            "num_themes": num_themes,
            "kept": True,
            "cost": cost,
            "tokens": tokens,
        })

        # Mutation loop
        for i in range(1, NUM_ITERATIONS + 1):
            print(f"\nIteration {i}/{NUM_ITERATIONS}: mutating prompt...")
            mutation_desc, new_prompt, mut_tokens, mut_cost = await mutate_prompt(client, current_prompt, score)
            total_cost += mut_cost
            total_tokens += mut_tokens
            print(f"  Mutation: {mutation_desc}")

            print(f"Iteration {i}/{NUM_ITERATIONS}: running theme detection ({len(batches)} batches)...")
            assignments, det_tokens, det_cost = await run_theme_detection(client, papers, batches, new_prompt)
            total_cost += det_cost
            total_tokens += det_tokens

            new_score, mean_intra, mean_inter, num_themes = compute_score(assignments, embeddings)
            print(f"Iteration {i}/{NUM_ITERATIONS}: scoring... S={new_score:.4f} (intra={mean_intra:.4f}, inter={mean_inter:.4f}, {num_themes} themes)")

            kept = new_score > score
            if kept:
                print(f"Iteration {i}/{NUM_ITERATIONS}: KEEP ({new_score:.4f} > {score:.4f})")
                current_prompt = new_prompt
                score = new_score
                if new_score > best_score:
                    best_score = new_score
                    best_prompt = new_prompt
            else:
                print(f"Iteration {i}/{NUM_ITERATIONS}: REVERT ({new_score:.4f} <= {score:.4f})")

            iterations_log.append({
                "iteration": i,
                "prompt_summary": new_prompt[:200],
                "mutation": mutation_desc,
                "score": new_score,
                "mean_intra": mean_intra,
                "mean_inter": mean_inter,
                "num_themes": num_themes,
                "kept": kept,
                "cost": mut_cost + det_cost,
                "tokens": mut_tokens + det_tokens,
            })

            # Save results and regenerate report after each iteration
            save_results(iterations_log, best_score, baseline_score, total_cost, total_tokens)
            save_best_prompt(best_prompt)
            generate_report()

    save_results(iterations_log, best_score, baseline_score, total_cost, total_tokens)
    save_best_prompt(best_prompt)
    generate_report()
    print_summary(iterations_log, best_score, baseline_score, total_cost, total_tokens)


# ============================================================================
# MAIN LOGIC
# ============================================================================

async def mutate_prompt(
    client: httpx.AsyncClient,
    current_prompt: str,
    current_score: float,
) -> tuple[str, str, int, float]:
    """
    Ask the LLM to suggest a mutation and rewrite the prompt.

    Args:
        client: httpx async client
        current_prompt: the current theme detection prompt
        current_score: the current discrimination score

    Returns:
        (mutation_description, new_prompt, tokens_used, cost)
    """
    mutation_request = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are optimizing a research paper classification prompt. "
                    f"The current discrimination score (mean_intra/mean_inter cosine similarity) is {current_score:.4f}. "
                    "Higher is better -- it means papers within a theme are more similar to each other "
                    "than papers across themes. Suggest a specific change to improve theme coherence "
                    "and distinctness. Then rewrite the full prompt with your change applied."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Current prompt:\n\n{current_prompt}\n\n"
                    "Respond with JSON:\n"
                    '{\n'
                    '  "mutation": "short description of what you changed",\n'
                    '  "new_prompt": "the full rewritten prompt"\n'
                    '}'
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.8,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    resp = await client.post(OPENROUTER_URL, json=mutation_request, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"OpenRouter API error: {data['error']}")

    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)

    usage = data.get("usage", {})
    tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    cost = (
        usage.get("prompt_tokens", 0) * COST_PER_INPUT_TOKEN
        + usage.get("completion_tokens", 0) * COST_PER_OUTPUT_TOKEN
    )

    return parsed["mutation"], parsed["new_prompt"], tokens, cost


async def run_theme_detection(
    client: httpx.AsyncClient,
    papers: list[dict],
    batches: list[list[dict]],
    prompt_instructions: str,
) -> tuple[dict, int, float]:
    """
    Run theme detection on all papers using the given prompt instructions.
    Batches papers into groups; batches 2+ receive the theme list from batch 1.

    Args:
        client: httpx async client
        papers: all papers (for reference)
        batches: pre-split batches of papers
        prompt_instructions: the theme detection instructions (without paper list)

    Returns:
        (assignments_dict, tokens_used, cost)
        assignments_dict maps arxiv_id -> list of theme names
    """
    all_assignments: dict[str, list[str]] = {}
    theme_list: list[str] = []
    total_tokens = 0
    total_cost = 0.0

    for batch_idx, batch in enumerate(batches):
        prompt = build_detection_prompt(batch, prompt_instructions, theme_list if batch_idx > 0 else None)

        for attempt in range(2):
            try:
                resp_data = await send_llm_request(client, prompt)
                break
            except Exception as e:
                if attempt == 0:
                    print(f"    WARNING: batch {batch_idx + 1} failed: {e}. Retrying...")
                    await asyncio.sleep(2)
                else:
                    print(f"    WARNING: batch {batch_idx + 1} failed twice. Skipping.")
                    resp_data = None

        if resp_data is None:
            continue

        usage = resp_data.get("usage", {})
        tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        cost = (
            usage.get("prompt_tokens", 0) * COST_PER_INPUT_TOKEN
            + usage.get("completion_tokens", 0) * COST_PER_OUTPUT_TOKEN
        )
        total_tokens += tokens
        total_cost += cost

        content = resp_data["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        # Extract theme names from first batch
        if batch_idx == 0:
            for theme in parsed.get("themes", []):
                name = theme if isinstance(theme, str) else theme.get("name", "")
                if name and name not in theme_list:
                    theme_list.append(name)

        # Collect assignments
        for a in parsed.get("assignments", []):
            arxiv_id = a.get("arxiv_id", "")
            themes = a.get("themes", [])
            if arxiv_id:
                all_assignments[arxiv_id] = themes
                # Track any new theme names
                for t in themes:
                    if t not in theme_list:
                        theme_list.append(t)

    return all_assignments, total_tokens, total_cost


async def send_llm_request(client: httpx.AsyncClient, prompt: str) -> dict:
    """
    Send a request to OpenRouter and return the parsed response.

    Args:
        prompt: the user prompt

    Returns:
        Full API response dict
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
# SCORING
# ============================================================================

def compute_score(
    assignments: dict[str, list[str]],
    embeddings: dict[str, list[float]],
) -> tuple[float, float, float, int]:
    """
    Compute the discrimination score S = mean_intra / mean_inter.

    Args:
        assignments: arxiv_id -> list of theme names
        embeddings: arxiv_id -> embedding vector

    Returns:
        (score, mean_intra, mean_inter, num_themes)
    """
    # Group papers by theme
    theme_papers: dict[str, list[str]] = {}
    for arxiv_id, themes in assignments.items():
        for theme in themes:
            if theme not in theme_papers:
                theme_papers[theme] = []
            theme_papers[theme].append(arxiv_id)

    # Filter themes with >= 2 papers that have embeddings
    valid_themes: dict[str, np.ndarray] = {}
    for theme, paper_ids in theme_papers.items():
        vecs = []
        for pid in paper_ids:
            if pid in embeddings:
                vecs.append(embeddings[pid])
        if len(vecs) >= 2:
            matrix = np.array(vecs)
            # Normalize rows for cosine similarity
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            valid_themes[theme] = matrix / norms

    if len(valid_themes) < 2:
        return 0.0, 0.0, 0.0, len(valid_themes)

    # Mean intra-theme cosine similarity
    intra_sims = []
    for theme, normed in valid_themes.items():
        sim_matrix = normed @ normed.T
        n = sim_matrix.shape[0]
        # Extract upper triangle (exclude diagonal)
        upper_indices = np.triu_indices(n, k=1)
        pairwise = sim_matrix[upper_indices]
        if len(pairwise) > 0:
            intra_sims.append(float(np.mean(pairwise)))

    # Mean inter-theme cosine similarity (between theme centroids)
    theme_names = list(valid_themes.keys())
    centroids = []
    for name in theme_names:
        centroid = np.mean(valid_themes[name], axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        centroids.append(centroid)

    centroid_matrix = np.array(centroids)
    inter_sim_matrix = centroid_matrix @ centroid_matrix.T
    n_themes = inter_sim_matrix.shape[0]
    upper_indices = np.triu_indices(n_themes, k=1)
    inter_pairwise = inter_sim_matrix[upper_indices]

    mean_intra = float(np.mean(intra_sims)) if intra_sims else 0.0
    mean_inter = float(np.mean(inter_pairwise)) if len(inter_pairwise) > 0 else 0.0

    score = mean_intra / mean_inter if mean_inter > 0 else 0.0

    return score, mean_intra, mean_inter, len(valid_themes)


# ============================================================================
# PROMPT BUILDING
# ============================================================================

def build_detection_prompt(
    papers: list[dict],
    instructions: str,
    existing_themes: list[str] | None,
) -> str:
    """
    Build the theme detection prompt for a batch of papers.

    Args:
        papers: batch of paper dicts
        instructions: the prompt instructions (what we're optimizing)
        existing_themes: theme names from batch 1 (None for batch 1 itself)

    Returns:
        The full prompt string
    """
    papers_text = format_papers(papers)

    if existing_themes:
        theme_list_str = "\n".join(f"- {t}" for t in existing_themes)
        return (
            f"{instructions}\n\n"
            f"Use the following existing themes where applicable (you may add new ones if needed):\n"
            f"{theme_list_str}\n\n"
            f"Papers:\n{papers_text}\n\n"
            f"Respond with JSON:\n"
            f'{{\n'
            f'  "assignments": [\n'
            f'    {{"arxiv_id": "2603.12345", "themes": ["Theme 1", "Theme 2"]}}\n'
            f'  ]\n'
            f'}}\n'
            f"Every paper must be assigned to at least one theme."
        )

    return (
        f"{instructions}\n\n"
        f"Papers:\n{papers_text}\n\n"
        f"Respond with JSON:\n"
        f'{{\n'
        f'  "themes": [\n'
        f'    {{"name": "Theme Name", "description": "Brief description"}}\n'
        f'  ],\n'
        f'  "assignments": [\n'
        f'    {{"arxiv_id": "2603.12345", "themes": ["Theme 1", "Theme 2"]}}\n'
        f'  ]\n'
        f'}}\n'
        f"Every paper must be assigned to at least one theme."
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_all_papers() -> list[dict]:
    """Load all papers from papers_by_week.json into a flat list."""
    if not PAPERS_FILE.exists():
        raise FileNotFoundError(f"Papers file not found: {PAPERS_FILE}")

    with open(PAPERS_FILE) as f:
        raw = json.load(f)

    papers = []
    for week_obj in raw["weeks"]:
        papers.extend(week_obj["papers"])
    return papers


def load_embeddings() -> dict[str, list[float]]:
    """Load embeddings from output/embeddings.json."""
    if not EMBEDDINGS_FILE.exists():
        raise FileNotFoundError(f"Embeddings file not found: {EMBEDDINGS_FILE}")

    with open(EMBEDDINGS_FILE) as f:
        return json.load(f)


def create_batches(papers: list[dict]) -> list[list[dict]]:
    """Split papers into batches of ~BATCH_SIZE."""
    if len(papers) <= BATCH_SIZE:
        return [papers]

    batches = []
    for i in range(0, len(papers), BATCH_SIZE):
        batches.append(papers[i : i + BATCH_SIZE])
    return batches


def format_papers(papers: list[dict]) -> str:
    """Format papers into a string for the LLM prompt."""
    lines = []
    for p in papers:
        arxiv_id = p.get("arxiv_id", "unknown")
        title = p.get("title", "No title")
        abstract = p.get("abstract") or "No abstract"
        if len(abstract) > 500:
            abstract = abstract[:500] + "..."
        lines.append(f"[{arxiv_id}] {title}\nAbstract: {abstract}\n")
    return "\n".join(lines)


def save_results(
    iterations: list[dict],
    best_score: float,
    baseline_score: float,
    total_cost: float,
    total_tokens: int,
) -> None:
    """Save loop results to output/loop_results.json."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "iterations": iterations,
        "best_score": best_score,
        "baseline_score": baseline_score,
        "total_cost": total_cost,
        "total_tokens": total_tokens,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved results to {OUTPUT_FILE}")


def generate_report() -> None:
    """Regenerate the HTML report from the current loop_results.json."""
    import subprocess
    import sys
    report_script = SCRIPT_DIR / "04_generate_report.py"
    if report_script.exists():
        subprocess.run([sys.executable, str(report_script)], cwd=str(SCRIPT_DIR), capture_output=True)


def save_best_prompt(prompt: str) -> None:
    """Save the best prompt to output/best_prompt.txt."""
    BEST_PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(BEST_PROMPT_FILE, "w") as f:
        f.write(prompt)

    print(f"Saved best prompt to {BEST_PROMPT_FILE}")


def print_summary(
    iterations: list[dict],
    best_score: float,
    baseline_score: float,
    total_cost: float,
    total_tokens: int,
) -> None:
    """Print a summary table of all iterations."""
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"{'Iter':<6}{'Score':<10}{'Intra':<10}{'Inter':<10}{'Themes':<10}{'Kept':<8}{'Cost':<10}{'Mutation'}")
    print(f"{'-'*80}")

    for it in iterations:
        kept_str = "YES" if it["kept"] else "NO"
        mutation_short = it["mutation"][:30]
        print(
            f"{it['iteration']:<6}"
            f"{it['score']:<10.4f}"
            f"{it['mean_intra']:<10.4f}"
            f"{it['mean_inter']:<10.4f}"
            f"{it['num_themes']:<10}"
            f"{kept_str:<8}"
            f"${it['cost']:<9.4f}"
            f"{mutation_short}"
        )

    print(f"{'-'*80}")
    print(f"Baseline: {baseline_score:.4f} | Best: {best_score:.4f} | "
          f"Improvement: {((best_score / baseline_score - 1) * 100) if baseline_score > 0 else 0:.1f}%")
    print(f"Total cost: ${total_cost:.4f} | Total tokens: {total_tokens}")


if __name__ == "__main__":
    asyncio.run(main())
