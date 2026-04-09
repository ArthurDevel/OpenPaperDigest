"""
Score the quality of theme assignments using embedding-based discrimination.

Computes a discrimination score S = mean_intra / mean_inter, where:
- mean_intra: average within-theme cosine similarity (theme coherence)
- mean_inter: average between-theme cosine similarity (theme overlap)

A higher score means themes are more internally coherent relative to how
much they overlap with each other. Score > 1 means themes are meaningful.

Responsibilities:
- Load embeddings and theme assignments from local JSON files
- Build theme -> paper mappings across all weeks
- Compute per-theme coherence (intra-theme similarity)
- Compute inter-theme similarity with sampling for large pair counts
- Output scored results to output/theme_scores.json
"""

import json
import os
import random
from itertools import combinations
from pathlib import Path

import numpy as np

# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
EMBEDDINGS_PATH = SCRIPT_DIR / "output" / "embeddings.json"
THEME_ASSIGNMENTS_PATH = (
    SCRIPT_DIR / ".." / "research-frontiers-detection" / "output" / "theme_assignments.json"
)
OUTPUT_PATH = SCRIPT_DIR / "output" / "theme_scores.json"

MIN_PAPERS_PER_THEME = 2
MAX_CROSS_PAIRS_BEFORE_SAMPLING = 100_000
SAMPLE_SIZE_PER_THEME_PAIR = 1000


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    embeddings, theme_to_ids = load_data()
    theme_to_ids = filter_themes(theme_to_ids, embeddings)

    if len(theme_to_ids) < 2:
        raise ValueError(f"Need at least 2 themes with >= {MIN_PAPERS_PER_THEME} papers. Got {len(theme_to_ids)}.")

    theme_embeddings = build_theme_embeddings(theme_to_ids, embeddings)

    per_theme_coherence = compute_per_theme_coherence(theme_embeddings)
    mean_intra = np.mean([c for _, c in per_theme_coherence])

    mean_inter = compute_mean_inter(theme_embeddings)

    if mean_inter == 0:
        raise ValueError("mean_inter is 0, cannot compute score.")

    score = mean_intra / mean_inter

    all_paper_ids = set()
    for ids in theme_to_ids.values():
        all_paper_ids.update(ids)

    results = build_results(score, mean_intra, mean_inter, theme_to_ids, all_paper_ids, per_theme_coherence)
    save_and_print(results, mean_inter)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_data():
    """Load embeddings and theme assignments from JSON files.

    Returns:
        tuple: (embeddings dict, theme_to_ids dict mapping theme name -> list of arxiv_ids)
    """
    with open(EMBEDDINGS_PATH, "r") as f:
        embeddings = json.load(f)

    with open(THEME_ASSIGNMENTS_PATH, "r") as f:
        theme_data = json.load(f)

    # Build theme_name -> [arxiv_ids] across all weeks
    theme_to_ids = {}
    weekly = theme_data.get("weekly_assignments", {})
    for week, papers in weekly.items():
        for paper in papers:
            arxiv_id = paper.get("arxiv_id")
            themes = paper.get("themes", [])
            for theme in themes:
                if theme not in theme_to_ids:
                    theme_to_ids[theme] = []
                theme_to_ids[theme].append(arxiv_id)

    # Deduplicate ids per theme
    for theme in theme_to_ids:
        theme_to_ids[theme] = list(set(theme_to_ids[theme]))

    return embeddings, theme_to_ids


def filter_themes(theme_to_ids, embeddings):
    """Remove themes with fewer than MIN_PAPERS_PER_THEME papers that have embeddings.

    Args:
        theme_to_ids: dict mapping theme name -> list of arxiv_ids
        embeddings: dict mapping arxiv_id -> embedding vector

    Returns:
        dict: filtered theme_to_ids with only papers that have embeddings
    """
    filtered = {}
    for theme, ids in theme_to_ids.items():
        ids_with_emb = [aid for aid in ids if aid in embeddings]
        if len(ids_with_emb) >= MIN_PAPERS_PER_THEME:
            filtered[theme] = ids_with_emb
    return filtered


def build_theme_embeddings(theme_to_ids, embeddings):
    """Build a dict mapping theme name -> numpy array of embeddings.

    Args:
        theme_to_ids: dict mapping theme name -> list of arxiv_ids
        embeddings: dict mapping arxiv_id -> embedding vector

    Returns:
        dict: theme name -> np.ndarray of shape (num_papers, embedding_dim)
    """
    theme_embeddings = {}
    for theme, ids in theme_to_ids.items():
        vecs = [embeddings[aid] for aid in ids]
        theme_embeddings[theme] = np.array(vecs)
    return theme_embeddings


def cosine_similarity_matrix(a, b):
    """Compute cosine similarity between all pairs of rows in a and b.

    Args:
        a: np.ndarray of shape (n, d)
        b: np.ndarray of shape (m, d)

    Returns:
        np.ndarray of shape (n, m) with cosine similarities
    """
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    return a_norm @ b_norm.T


def compute_per_theme_coherence(theme_embeddings):
    """Compute average pairwise cosine similarity within each theme.

    Args:
        theme_embeddings: dict mapping theme name -> np.ndarray of embeddings

    Returns:
        list of (theme_name, coherence_score) tuples, sorted by coherence descending
    """
    results = []
    for theme, embs in theme_embeddings.items():
        sim_matrix = cosine_similarity_matrix(embs, embs)
        n = len(embs)
        # Extract upper triangle (exclude diagonal)
        upper_indices = np.triu_indices(n, k=1)
        pairwise_sims = sim_matrix[upper_indices]
        coherence = float(np.mean(pairwise_sims))
        results.append((theme, coherence))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def compute_mean_inter(theme_embeddings):
    """Compute average cosine similarity between all pairs of different themes.

    Uses sampling when the number of cross-pairs exceeds the threshold.

    Args:
        theme_embeddings: dict mapping theme name -> np.ndarray of embeddings

    Returns:
        float: mean inter-theme similarity
    """
    themes = list(theme_embeddings.keys())
    pair_avgs = []

    for theme_a, theme_b in combinations(themes, 2):
        embs_a = theme_embeddings[theme_a]
        embs_b = theme_embeddings[theme_b]
        num_cross_pairs = len(embs_a) * len(embs_b)

        if num_cross_pairs > MAX_CROSS_PAIRS_BEFORE_SAMPLING:
            # Sample random pairs
            sims = []
            for _ in range(SAMPLE_SIZE_PER_THEME_PAIR):
                i = random.randint(0, len(embs_a) - 1)
                j = random.randint(0, len(embs_b) - 1)
                a_vec = embs_a[i]
                b_vec = embs_b[j]
                cos_sim = np.dot(a_vec, b_vec) / (np.linalg.norm(a_vec) * np.linalg.norm(b_vec))
                sims.append(cos_sim)
            pair_avg = float(np.mean(sims))
        else:
            sim_matrix = cosine_similarity_matrix(embs_a, embs_b)
            pair_avg = float(np.mean(sim_matrix))

        pair_avgs.append(pair_avg)

    return float(np.mean(pair_avgs))


def build_results(score, mean_intra, mean_inter, theme_to_ids, all_paper_ids, per_theme_coherence):
    """Build the output results dict.

    Args:
        score: overall discrimination score
        mean_intra: average intra-theme similarity
        mean_inter: average inter-theme similarity
        theme_to_ids: dict mapping theme name -> list of arxiv_ids
        all_paper_ids: set of all paper ids with embeddings
        per_theme_coherence: list of (theme_name, coherence) tuples

    Returns:
        dict: results suitable for JSON serialization
    """
    per_theme_list = [
        {
            "theme": theme,
            "coherence": round(coherence, 4),
            "paper_count": len(theme_to_ids[theme]),
        }
        for theme, coherence in per_theme_coherence
    ]

    return {
        "score": round(score, 4),
        "mean_intra": round(mean_intra, 4),
        "mean_inter": round(mean_inter, 4),
        "num_themes": len(theme_to_ids),
        "num_papers_with_embeddings": len(all_paper_ids),
        "per_theme": per_theme_list,
    }


def save_and_print(results, mean_inter):
    """Save results to JSON and print a formatted summary.

    Args:
        results: dict with scoring results
        mean_inter: mean inter-theme similarity (used to flag weak themes)
    """
    os.makedirs(OUTPUT_PATH.parent, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Theme Discrimination Score: {results['score']}")
    print(f"  mean_intra: {results['mean_intra']}")
    print(f"  mean_inter: {results['mean_inter']}")
    print(f"  num_themes: {results['num_themes']}")
    print(f"  num_papers: {results['num_papers_with_embeddings']}")
    print()
    print(f"{'Theme':<50} {'Coherence':>10} {'Papers':>8}")
    print("-" * 70)

    for entry in results["per_theme"]:
        flag = " ** WEAK" if entry["coherence"] < mean_inter else ""
        print(f"{entry['theme']:<50} {entry['coherence']:>10.4f} {entry['paper_count']:>8}{flag}")

    weak_count = sum(1 for e in results["per_theme"] if e["coherence"] < mean_inter)
    if weak_count > 0:
        print()
        print(f"** {weak_count} theme(s) have coherence below mean_inter ({round(mean_inter, 4)})")

    print()
    print(f"Results saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
