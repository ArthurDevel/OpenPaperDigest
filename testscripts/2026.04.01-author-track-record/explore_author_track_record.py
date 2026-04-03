"""Explore whether author track record predicts paper quality (PageRank).

Loads PageRank scores from a previous testscript, queries the DB for
paper-author relationships, and computes per-author and per-paper
"author track record" scores. Tests correlation with PageRank.

Responsibilities:
- Load PageRank scores from ../2026.04.01-pagerank-quality-score/output/
- Query DB for paper -> author relationships (papers, paper_authors, authors)
- Compute per-author scores (median/mean/max PageRank of their papers)
- Compute per-paper "author track record" (best author's median PageRank)
- Output analysis: top papers, top authors, correlations, hidden gems
- Save results to output/
"""
import argparse
import bisect
import json
import os
import statistics
import sys
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv


# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
PAGERANK_FILE = os.path.join(
    SCRIPT_DIR, "..", "2026.04.01-pagerank-quality-score", "output", "pagerank_results.json"
)
TOP_N = 20


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main() -> None:
    """Main entrypoint: load data, compute scores, output analysis."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--multi-paper-only", action="store_true",
                        help="Filter to authors with 2+ papers (removes circularity)")
    args = parser.parse_args()

    load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set in .env")

    suffix = "_multi_paper" if args.multi_paper_only else ""
    output_file = os.path.join(OUTPUT_DIR, f"analysis{suffix}.txt")
    tee = TeeWriter(sys.stdout, open(output_file, "w"))
    sys.stdout = tee

    try:
        run_analysis(database_url, multi_paper_only=args.multi_paper_only)
    finally:
        sys.stdout = tee.original
        tee.file.close()
        print(f"\nAnalysis saved to {output_file}")


def run_analysis(database_url: str, multi_paper_only: bool = False) -> None:
    """Run the full analysis pipeline.

    @param database_url: PostgreSQL connection string
    @param multi_paper_only: If True, only consider authors with 2+ papers
    """
    # Step 1: Load PageRank scores
    print("Loading PageRank scores...")
    pagerank_data = load_json(PAGERANK_FILE)
    rankings = pagerank_data["rankings"]
    pagerank_by_s2id = {r["s2_paper_id"]: r["pagerank_score"] for r in rankings}
    print(f"  Loaded {len(rankings)} PageRank scores")
    print(f"  Score range: {min(pagerank_by_s2id.values()):.10f} - {max(pagerank_by_s2id.values()):.10f}\n")

    # Step 2: Query DB for paper-author relationships
    print("Querying database for paper-author relationships...")
    conn = psycopg2.connect(database_url)
    try:
        paper_authors, author_info = query_paper_authors(conn)
    finally:
        conn.close()

    print(f"  Papers with author links: {len(paper_authors)}")
    print(f"  Unique authors: {len(author_info)}\n")

    # Step 3: Compute per-author scores
    print("Computing per-author scores...")
    author_scores = compute_author_scores(paper_authors, pagerank_by_s2id)
    authors_with_scores = sum(1 for a in author_scores.values() if a["paper_count"] > 0)
    print(f"  Authors with at least 1 PageRank-scored paper: {authors_with_scores}")

    if multi_paper_only:
        multi_count = sum(1 for a in author_scores.values() if a["paper_count"] >= 2)
        print(f"  Authors with 2+ papers (multi-paper filter): {multi_count}")
        # Zero out single-paper authors so they don't contribute to track records
        for aid in list(author_scores.keys()):
            if author_scores[aid]["paper_count"] < 2:
                author_scores[aid] = {"median": 0.0, "mean": 0.0, "max": 0.0, "paper_count": author_scores[aid]["paper_count"]}
    print()

    # Step 4: Compute per-paper author track record
    print("Computing per-paper author track record scores...")
    paper_track_records = compute_paper_track_records(
        paper_authors, author_scores, author_info, pagerank_by_s2id
    )

    if multi_paper_only:
        # Only keep papers that have at least one multi-paper author
        paper_track_records = [p for p in paper_track_records if p["track_record"] > 0]

    print(f"  Papers with track record scores: {len(paper_track_records)}\n")

    # Step 5: Analysis output
    print_top_papers_by_track_record(paper_track_records)
    print_top_authors(author_scores, author_info, multi_paper_only)
    print_correlations(paper_track_records)
    print_hidden_gems(paper_track_records)

    # Step 6: Save outputs
    suffix = "_multi_paper" if multi_paper_only else ""
    save_author_scores(author_scores, author_info, suffix)
    save_paper_track_record_table(paper_track_records, suffix)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

class TeeWriter:
    """Write to both stdout and a file simultaneously.

    @param original: Original stdout stream
    @param file: File object to write to
    """
    def __init__(self, original, file):
        self.original = original
        self.file = file

    def write(self, data):
        self.original.write(data)
        self.file.write(data)

    def flush(self):
        self.original.flush()
        self.file.flush()


def load_json(path: str) -> dict:
    """Load and parse a JSON file.

    @param path: Absolute path to the JSON file
    @returns Parsed JSON content
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required file not found: {path}")
    with open(path, "r") as f:
        return json.load(f)


def query_paper_authors(conn) -> tuple[dict, dict]:
    """Query DB for paper-author relationships.

    @param conn: psycopg2 connection
    @returns Tuple of:
        - paper_authors: {s2_paper_id: [{"s2_author_id": ..., "author_order": ...}, ...]}
        - author_info: {s2_author_id: {"name": ..., "h_index": ...}}
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            p.s2_ids->>'s2_paper_id' AS s2_paper_id,
            p.arxiv_id,
            p.title,
            a.s2_author_id,
            a.name,
            a.h_index,
            pa.author_order
        FROM papers p
        JOIN paper_authors pa ON pa.paper_id = p.id
        JOIN authors a ON a.id = pa.author_id
        WHERE p.s2_ids->>'s2_paper_id' IS NOT NULL
          AND a.s2_author_id IS NOT NULL
        ORDER BY p.id, pa.author_order
    """)

    paper_authors = {}  # s2_paper_id -> list of author entries
    author_info = {}    # s2_author_id -> {name, h_index}

    for row in cursor:
        s2_paper_id, arxiv_id, title, s2_author_id, name, h_index, author_order = row

        if s2_paper_id not in paper_authors:
            paper_authors[s2_paper_id] = {
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": [],
            }
        paper_authors[s2_paper_id]["authors"].append({
            "s2_author_id": str(s2_author_id),
            "author_order": author_order,
        })

        author_info[str(s2_author_id)] = {
            "name": name,
            "h_index": h_index,
        }

    cursor.close()
    return paper_authors, author_info


def compute_author_scores(
    paper_authors: dict, pagerank_by_s2id: dict
) -> dict:
    """Compute per-author aggregate PageRank scores.

    For each author, collect PageRank scores of all their papers and compute
    median, mean, max, and count.

    @param paper_authors: {s2_paper_id: {"authors": [{"s2_author_id": ...}], ...}}
    @param pagerank_by_s2id: {s2_paper_id: pagerank_score}
    @returns {s2_author_id: {"median": ..., "mean": ..., "max": ..., "paper_count": ...}}
    """
    # Collect PageRank scores per author
    author_paper_scores = {}  # s2_author_id -> [pagerank_score, ...]

    for s2_paper_id, paper_data in paper_authors.items():
        pr_score = pagerank_by_s2id.get(s2_paper_id)
        if pr_score is None:
            continue

        for author_entry in paper_data["authors"]:
            aid = author_entry["s2_author_id"]
            if aid not in author_paper_scores:
                author_paper_scores[aid] = []
            author_paper_scores[aid].append(pr_score)

    # Compute aggregates
    author_scores = {}
    for aid, scores in author_paper_scores.items():
        author_scores[aid] = {
            "median": statistics.median(scores),
            "mean": statistics.mean(scores),
            "max": max(scores),
            "paper_count": len(scores),
        }

    # Include authors with 0 papers in pagerank
    all_author_ids = set()
    for paper_data in paper_authors.values():
        for a in paper_data["authors"]:
            all_author_ids.add(a["s2_author_id"])

    for aid in all_author_ids:
        if aid not in author_scores:
            author_scores[aid] = {
                "median": 0.0,
                "mean": 0.0,
                "max": 0.0,
                "paper_count": 0,
            }

    return author_scores


def compute_paper_track_records(
    paper_authors: dict,
    author_scores: dict,
    author_info: dict,
    pagerank_by_s2id: dict,
) -> list[dict]:
    """Compute per-paper author track record scores.

    For each paper, the "author track record" is the MAX of its authors'
    median PageRank scores (i.e., the best author's track record).

    @param paper_authors: {s2_paper_id: {"arxiv_id": ..., "title": ..., "authors": [...]}}
    @param author_scores: {s2_author_id: {"median": ..., ...}}
    @param author_info: {s2_author_id: {"name": ..., "h_index": ...}}
    @param pagerank_by_s2id: {s2_paper_id: pagerank_score}
    @returns List of paper track record dicts, sorted by track_record descending
    """
    results = []

    for s2_paper_id, paper_data in paper_authors.items():
        author_medians = []
        best_author_id = None
        best_median = -1

        for author_entry in paper_data["authors"]:
            aid = author_entry["s2_author_id"]
            median = author_scores.get(aid, {}).get("median", 0.0)
            author_medians.append(median)

            if median > best_median:
                best_median = median
                best_author_id = aid

        if not author_medians:
            continue

        best_info = author_info.get(best_author_id, {})

        results.append({
            "s2_paper_id": s2_paper_id,
            "arxiv_id": paper_data["arxiv_id"],
            "title": paper_data["title"],
            "track_record": max(author_medians),
            "mean_author_median": statistics.mean(author_medians),
            "paper_pagerank": pagerank_by_s2id.get(s2_paper_id, 0.0),
            "best_author_name": best_info.get("name", "Unknown"),
            "best_author_h_index": best_info.get("h_index"),
            "best_author_id": best_author_id,
            "num_authors": len(author_medians),
        })

    results.sort(key=lambda x: x["track_record"], reverse=True)

    # Compute percentiles using bisect for efficiency
    all_scores = sorted([r["track_record"] for r in results])
    n = len(all_scores)
    for r in results:
        rank = bisect.bisect_right(all_scores, r["track_record"])
        r["track_record_percentile"] = round(rank / n * 100, 1) if n > 0 else 0.0

    return results


def print_top_papers_by_track_record(paper_track_records: list[dict]) -> None:
    """Print top N papers ranked by author track record score.

    @param paper_track_records: Sorted list of paper track record dicts
    """
    print(f"{'='*100}")
    print(f"TOP {TOP_N} PAPERS BY AUTHOR TRACK RECORD")
    print(f"{'='*100}")

    for i, p in enumerate(paper_track_records[:TOP_N], 1):
        print(f"\n  {i:>2}. Track Record: {p['track_record']:.10f}  (P{p['track_record_percentile']})  |  Paper PageRank: {p['paper_pagerank']:.10f}")
        print(f"      Best Author: {p['best_author_name']} (h-index: {p['best_author_h_index']})")
        print(f"      arXiv: {p['arxiv_id'] or 'N/A'}  |  Authors: {p['num_authors']}")
        print(f"      Title: {(p['title'] or 'N/A')[:100]}")

    print()


def print_top_authors(author_scores: dict, author_info: dict, multi_paper_only: bool = False) -> None:
    """Print top N authors ranked by median PageRank.

    @param author_scores: {s2_author_id: {"median": ..., "mean": ..., ...}}
    @param author_info: {s2_author_id: {"name": ..., "h_index": ...}}
    @param multi_paper_only: If True, only show authors with 2+ papers
    """
    items = author_scores.items()
    if multi_paper_only:
        items = [(aid, s) for aid, s in items if s["paper_count"] >= 2]
    sorted_authors = sorted(
        items,
        key=lambda x: x[1]["median"],
        reverse=True,
    )

    print(f"{'='*100}")
    print(f"TOP {TOP_N} AUTHORS BY MEDIAN PAGERANK")
    print(f"{'='*100}")

    for i, (aid, scores) in enumerate(sorted_authors[:TOP_N], 1):
        info = author_info.get(aid, {})
        name = info.get("name", "Unknown")
        h_index = info.get("h_index", "N/A")
        print(
            f"  {i:>2}. {name:<40} "
            f"median={scores['median']:.10f}  "
            f"mean={scores['mean']:.10f}  "
            f"max={scores['max']:.10f}  "
            f"papers={scores['paper_count']}  "
            f"h-index={h_index}"
        )

    print()


def print_correlations(paper_track_records: list[dict]) -> None:
    """Print Pearson and Spearman correlations between author track record and paper PageRank.

    @param paper_track_records: List of paper track record dicts
    """
    # Filter to papers that have a non-zero PageRank (i.e., they appear in the graph)
    papers_with_pr = [p for p in paper_track_records if p["paper_pagerank"] > 0]

    print(f"{'='*100}")
    print("CORRELATION: AUTHOR TRACK RECORD vs PAPER PAGERANK")
    print(f"{'='*100}")
    print(f"  Papers with both track record and PageRank: {len(papers_with_pr)}")
    print(f"  Papers with track record but no PageRank: {len(paper_track_records) - len(papers_with_pr)}")

    if len(papers_with_pr) < 3:
        print("  Not enough data for correlation analysis.\n")
        return

    track_records = [p["track_record"] for p in papers_with_pr]
    pageranks = [p["paper_pagerank"] for p in papers_with_pr]

    try:
        from scipy.stats import pearsonr, spearmanr

        pearson_r, pearson_p = pearsonr(track_records, pageranks)
        spearman_r, spearman_p = spearmanr(track_records, pageranks)

        print(f"  Pearson r:  {pearson_r:.6f}  (p={pearson_p:.2e})")
        print(f"  Spearman r: {spearman_r:.6f}  (p={spearman_p:.2e})")
    except ImportError:
        print("  scipy not available, skipping correlation analysis.")

    # Also correlate with h-index
    papers_with_h = [p for p in papers_with_pr if p["best_author_h_index"] is not None]
    if len(papers_with_h) >= 3:
        h_indices = [p["best_author_h_index"] for p in papers_with_h]
        h_pageranks = [p["paper_pagerank"] for p in papers_with_h]
        try:
            from scipy.stats import pearsonr, spearmanr

            h_pearson_r, h_pearson_p = pearsonr(h_indices, h_pageranks)
            h_spearman_r, h_spearman_p = spearmanr(h_indices, h_pageranks)

            print(f"\n  COMPARISON: h-index vs Paper PageRank (for reference)")
            print(f"  Pearson r:  {h_pearson_r:.6f}  (p={h_pearson_p:.2e})")
            print(f"  Spearman r: {h_spearman_r:.6f}  (p={h_spearman_p:.2e})")
        except ImportError:
            pass

    print()


def print_hidden_gems(paper_track_records: list[dict]) -> None:
    """Print papers with high author track record but zero PageRank citations.

    These are "hidden gems" -- papers by strong authors that haven't been
    cited yet in the graph.

    @param paper_track_records: List of paper track record dicts
    """
    # Find the 75th percentile of track record scores
    all_track_records = sorted([p["track_record"] for p in paper_track_records])
    p75_idx = int(len(all_track_records) * 0.75)
    p75_threshold = all_track_records[min(p75_idx, len(all_track_records) - 1)]

    # Papers with 0 PageRank (not in citation graph) but high track record
    zero_pr_papers = [p for p in paper_track_records if p["paper_pagerank"] == 0]
    hidden_gems = [p for p in zero_pr_papers if p["track_record"] >= p75_threshold]

    print(f"{'='*100}")
    print("HIDDEN GEMS: HIGH AUTHOR TRACK RECORD, ZERO PAGERANK")
    print(f"{'='*100}")
    print(f"  75th percentile track record threshold: {p75_threshold:.10f}")
    print(f"  Papers with zero PageRank: {len(zero_pr_papers)}")
    print(f"  Hidden gems (zero PR + track record >= P75): {len(hidden_gems)}")

    if hidden_gems:
        print(f"\n  Top {min(TOP_N, len(hidden_gems))} hidden gems:")
        for i, p in enumerate(hidden_gems[:TOP_N], 1):
            print(f"\n    {i:>2}. Track Record: {p['track_record']:.10f}  (P{p['track_record_percentile']})")
            print(f"        Best Author: {p['best_author_name']} (h-index: {p['best_author_h_index']})")
            print(f"        arXiv: {p['arxiv_id'] or 'N/A'}")
            print(f"        Title: {(p['title'] or 'N/A')[:100]}")

    print()


def save_author_scores(author_scores: dict, author_info: dict, suffix: str = "") -> None:
    """Save author scores to output/author_scores.json.

    @param author_scores: {s2_author_id: {"median": ..., ...}}
    @param author_info: {s2_author_id: {"name": ..., "h_index": ...}}
    @param suffix: Filename suffix (e.g. "_multi_paper")
    """
    output = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_authors": len(author_scores),
            "authors_with_scores": sum(1 for a in author_scores.values() if a["paper_count"] > 0),
        },
        "authors": {
            aid: {
                **scores,
                "name": author_info.get(aid, {}).get("name", "Unknown"),
                "h_index": author_info.get(aid, {}).get("h_index"),
            }
            for aid, scores in author_scores.items()
        },
    }

    path = os.path.join(OUTPUT_DIR, f"author_scores{suffix}.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Author scores saved to {path}")


def save_paper_track_record_table(paper_track_records: list[dict], suffix: str = "") -> None:
    """Save markdown table of papers ranked by author track record.

    @param paper_track_records: Sorted list of paper track record dicts
    @param suffix: Filename suffix (e.g. "_multi_paper")
    """
    lines = [
        "# Papers Ranked by Author Track Record",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total papers: {len(paper_track_records)}",
        "",
        "| Rank | Author Track Record | Percentile | Paper PageRank | Best Author | Best Author h-index | arXiv ID | Title |",
        "|------|--------------------:|-----------:|---------------:|-------------|--------------------:|----------|-------|",
    ]

    for i, p in enumerate(paper_track_records, 1):
        title = (p["title"] or "N/A")[:80]
        arxiv = p["arxiv_id"] or "N/A"
        h_index = p["best_author_h_index"] if p["best_author_h_index"] is not None else "N/A"
        pct = p.get("track_record_percentile", 0.0)
        lines.append(
            f"| {i} | {p['track_record']:.10f} | P{pct} | {p['paper_pagerank']:.10f} | "
            f"{p['best_author_name']} | {h_index} | {arxiv} | {title} |"
        )

    path = os.path.join(OUTPUT_DIR, f"paper_author_track_record{suffix}.md")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Paper track record table saved to {path}")


if __name__ == "__main__":
    main()
