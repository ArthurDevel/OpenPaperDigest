"""Calculate PageRank scores for academic papers from citation edges.

Reads citation edges and paper index, builds a directed citation graph,
runs PageRank, and outputs ranked results with statistics.

Responsibilities:
- Load citation edges and paper index from output/
- Build directed graph (citing -> cited)
- Run PageRank algorithm
- Print top papers, score distribution, and graph statistics
- Save full results to output/pagerank_results.json
"""
import json
import os
import statistics
from datetime import datetime, timezone

import networkx as nx


# ============================================================================
# CONSTANTS
# ============================================================================

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
TOP_N = 20
PAGERANK_ALPHA = 0.85
PAGERANK_MAX_ITER = 100


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main() -> None:
    """Main entrypoint: load data, build graph, run PageRank, output results."""
    # Step 1: Load data
    edges_data = load_json(os.path.join(OUTPUT_DIR, "citation_edges.json"))
    paper_index = load_json(os.path.join(OUTPUT_DIR, "paper_index.json"))

    edges = edges_data["edges"]
    metadata = edges_data["metadata"]
    print(f"Loaded {len(edges)} citation edges from {metadata['total_papers_queried']} queried papers")
    print(f"Paper index contains {len(paper_index)} papers from our DB\n")

    # Step 2: Build graph
    graph = build_citation_graph(edges)
    print(f"Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges\n")

    # Step 3: Run PageRank
    print("Running PageRank...")
    scores = nx.pagerank(graph, alpha=PAGERANK_ALPHA, max_iter=PAGERANK_MAX_ITER)
    print(f"PageRank computed for {len(scores)} nodes\n")

    # Step 4: Sort by score
    sorted_papers = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Step 5: Count in-degree (citation count) for each node
    in_degrees = dict(graph.in_degree())

    # Step 6: Print top papers
    print_top_papers(sorted_papers, paper_index, in_degrees)

    # Step 7: Print statistics
    print_score_statistics(scores, paper_index, graph)

    # Step 8: Save results
    save_results(sorted_papers, paper_index, in_degrees, metadata, graph)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_json(path: str) -> dict:
    """Load and parse a JSON file.

    @param path: Absolute path to the JSON file
    @returns Parsed JSON content
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required file not found: {path}")

    with open(path, "r") as f:
        return json.load(f)


def build_citation_graph(edges: list[dict]) -> nx.DiGraph:
    """Build a directed graph from citation edges.

    Edge direction: source (citing paper) -> target (cited paper).

    @param edges: List of {"source": ..., "target": ...} dicts
    @returns Directed graph
    """
    graph = nx.DiGraph()
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"])
    return graph


def print_top_papers(
    sorted_papers: list[tuple[str, float]],
    paper_index: dict,
    in_degrees: dict,
) -> None:
    """Print the top N papers by PageRank score.

    @param sorted_papers: Papers sorted by score descending
    @param paper_index: Mapping of s2_paper_id -> {arxiv_id, title}
    @param in_degrees: Mapping of node -> in-degree (citation count in graph)
    """
    print(f"{'='*80}")
    print(f"TOP {TOP_N} PAPERS BY PAGERANK SCORE")
    print(f"{'='*80}")

    for rank, (paper_id, score) in enumerate(sorted_papers[:TOP_N], 1):
        info = paper_index.get(paper_id, {})
        title = info.get("title", "(not in our DB)")
        arxiv_id = info.get("arxiv_id", "")
        citations = in_degrees.get(paper_id, 0)
        in_db = "  [ours]" if paper_id in paper_index else ""

        print(f"\n  {rank:>2}. Score: {score:.8f}  |  Citations (in graph): {citations}{in_db}")
        print(f"      S2 ID: {paper_id}")
        if arxiv_id:
            print(f"      arXiv: {arxiv_id}")
        print(f"      Title: {title[:100]}")

    print()


def print_score_statistics(
    scores: dict[str, float],
    paper_index: dict,
    graph: nx.DiGraph,
) -> None:
    """Print score distribution stats and graph coverage info.

    @param scores: PageRank scores for all nodes
    @param paper_index: Our DB papers
    @param graph: The citation graph
    """
    all_scores = sorted(scores.values())

    print(f"{'='*80}")
    print("SCORE DISTRIBUTION")
    print(f"{'='*80}")
    print(f"  Min:    {all_scores[0]:.10f}")
    print(f"  Max:    {all_scores[-1]:.10f}")
    print(f"  Mean:   {statistics.mean(all_scores):.10f}")
    print(f"  Median: {statistics.median(all_scores):.10f}")

    p90_idx = int(len(all_scores) * 0.90)
    p95_idx = int(len(all_scores) * 0.95)
    p99_idx = int(len(all_scores) * 0.99)
    print(f"  P90:    {all_scores[min(p90_idx, len(all_scores)-1)]:.10f}")
    print(f"  P95:    {all_scores[min(p95_idx, len(all_scores)-1)]:.10f}")
    print(f"  P99:    {all_scores[min(p99_idx, len(all_scores)-1)]:.10f}")

    # Coverage
    our_papers_in_graph = sum(1 for pid in paper_index if pid in scores)
    print(f"\n{'='*80}")
    print("GRAPH COVERAGE")
    print(f"{'='*80}")
    print(f"  Total nodes in graph:     {graph.number_of_nodes()}")
    print(f"  Total edges in graph:     {graph.number_of_edges()}")
    print(f"  Our DB papers in graph:   {our_papers_in_graph} / {len(paper_index)}")
    print(f"  External papers in graph: {graph.number_of_nodes() - our_papers_in_graph}")
    print()


def save_results(
    sorted_papers: list[tuple[str, float]],
    paper_index: dict,
    in_degrees: dict,
    source_metadata: dict,
    graph: nx.DiGraph,
) -> None:
    """Save full PageRank results to output/pagerank_results.json.

    @param sorted_papers: Papers sorted by score descending
    @param paper_index: Our DB papers
    @param in_degrees: In-degree counts
    @param source_metadata: Metadata from the citation edges file
    @param graph: The citation graph
    """
    all_scores = [s for _, s in sorted_papers]

    results = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source_metadata,
            "graph": {
                "total_nodes": graph.number_of_nodes(),
                "total_edges": graph.number_of_edges(),
                "our_papers_in_graph": sum(1 for pid in paper_index if pid in dict(sorted_papers)),
                "total_our_papers": len(paper_index),
            },
            "pagerank_params": {
                "alpha": PAGERANK_ALPHA,
                "max_iter": PAGERANK_MAX_ITER,
            },
            "score_distribution": {
                "min": all_scores[-1] if all_scores else 0,
                "max": all_scores[0] if all_scores else 0,
                "mean": statistics.mean(all_scores) if all_scores else 0,
                "median": statistics.median(all_scores) if all_scores else 0,
            },
        },
        "rankings": [
            {
                "rank": rank,
                "s2_paper_id": paper_id,
                "pagerank_score": score,
                "citations_in_graph": in_degrees.get(paper_id, 0),
                "in_our_db": paper_id in paper_index,
                "arxiv_id": paper_index.get(paper_id, {}).get("arxiv_id"),
                "title": paper_index.get(paper_id, {}).get("title"),
            }
            for rank, (paper_id, score) in enumerate(sorted_papers, 1)
        ],
    }

    path = os.path.join(OUTPUT_DIR, "pagerank_results.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Full results saved to {path}")


if __name__ == "__main__":
    main()
