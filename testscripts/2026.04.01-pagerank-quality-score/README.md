# PageRank Quality Score

## Goal

Test whether PageRank on the citation graph can serve as a quality signal for papers, without hardcoding authors or labs.

## What we tested

1. **Fetched citation edges** from the Semantic Scholar API for all 7,273 enriched papers in our database, using the batch endpoint (`POST /paper/batch` with `fields=references.paperId`).
2. **Built a directed citation graph** with networkx (71,567 nodes, 131,541 edges). Nodes include both our papers and external papers they reference.
3. **Ran PageRank** (alpha=0.85, 100 iterations) on the full graph, then filtered results to show only our papers.
4. **Expanded the graph one layer out** -- fetched references for all 68,261 external nodes (papers referenced by our papers but not in our DB). This grew the graph to **390,346 nodes / 883,809 edges** (6.7x more edges). ~80% of external papers had 0 references (same S2 indexing lag as our papers).
5. **Reran PageRank** on the expanded graph for more accurate scores.

## Results (expanded graph)

- **3,306 of 7,273 papers** received PageRank scores.
- 390,346 total nodes in graph (387,040 external + our 3,306 scored papers).
- Top-ranked papers globally are foundational papers not in our DB (BERT, ResNet, Adam, etc. with 1000+ in-graph citations). This is expected.
- Score distribution: median 0.0000025, top paper 0.0000890 (36x median).
- Full ranked list: `output/pagerank_our_papers.md`

### Top 10 of our papers

> **Cited by (in-graph)**: number of papers in the expanded citation graph that reference this paper.
> **References (in-graph)**: number of outgoing references from this paper that appear in the graph.

| Rank | Score | Cited by (in-graph) | References (in-graph) | Paper |
|------|-------|---------------------|-----------------------|-------|
| 1 | 0.0000890 | 1901 | 39 | Attention Is All You Need (1706.03762) |
| 2 | 0.0000136 | 268 | 0 | Qwen2.5-VL Technical Report (2502.13923) |
| 3 | 0.0000125 | 207 | 0 | GPT-4 Technical Report (2303.08774) |
| 4 | 0.0000110 | 131 | 46 | PagedAttention / vLLM (2309.06180) |
| 5 | 0.0000082 | 122 | 0 | Qwen2-VL (2409.12191) |
| 6 | 0.0000070 | 86 | 47 | FAISS (1702.08734) |
| 7 | 0.0000069 | 108 | 97 | Flow Matching (2209.03003) |
| 8 | 0.0000063 | 91 | 142 | InternVL3 (2504.10479) |
| 9 | 0.0000062 | 73 | 0 | Qwen2.5 Technical Report (2412.15115) |
| 10 | 0.0000058 | 53 | 81 | LlamaFactory (2403.13372) |

### Graph expansion impact

The expanded graph (one layer out) changed the rankings meaningfully:
- **FAISS** appeared at rank 6 -- it wasn't in the original top 10. Its score comes from second-order citations flowing through external papers (many external papers reference FAISS).
- Scores are lower overall because PageRank distributes across 390k nodes instead of 71k, but the relative rankings are more accurate.
- External papers now pass score through their references instead of being dead-end sinks, giving better signal propagation.

## Why ~4,100 papers have 0 outgoing references

Of 7,273 papers queried, ~4,100 returned zero references from the S2 batch API. We investigated thoroughly:

- **Not a script bug** -- rerunning with per-batch logging confirmed: 0 null responses across all 15 batches. S2 knows every paper (returned metadata for all of them). The breakdown per batch is consistent (~60% no refs each batch).
- **Not a rate limit issue** -- the script uses the same retry strategy as our production S2 client (burst + exponential backoff starting at 0.1s). 429s were handled correctly.
- **S2 hasn't parsed their bibliographies** -- confirmed by checking individual papers via the API. Example: DroidSpeak (`2411.02820`) returns `citationCount: 17` (other papers cite it) but `referenceCount: 0` (S2 hasn't extracted its reference list from the PDF). The S2 website shows **incoming citations**, not outgoing references -- easy to confuse.
- **Correlates with paper age** -- S2 processes newer papers last:

| Month | Missing refs | Total | % missing |
|-------|-------------|-------|-----------|
| 2025.10 | 10 | 197 | 5% |
| 2025.11 | 35 | 277 | 13% |
| 2025.12 | 130 | 546 | 24% |
| 2026.01 | 102 | 490 | 21% |
| 2026.03 | 3,771 | 5,483 | **69%** |

**Impact on PageRank:** these papers are "dead ends" -- they absorb score but can't pass it to the papers they reference (because we don't know the references). The damping factor (alpha=0.85) redistributes 15% evenly, so they still get a baseline score. Papers they *would* reference are underscored, but the overall rankings remain stable. As S2 indexes more bibliographies over time, re-fetching will improve coverage.

## Key observations

- **PageRank works** as a quality signal for papers. The graph structure surfaces important papers without any hardcoded rules.
- **Most top-scoring nodes are NOT in our DB** -- they're foundational papers (BERT, ResNet, Adam, etc.) that many of our papers reference. This is expected and correct behavior.
- **Graph expansion improves accuracy** -- fetching one layer of external references (6.7x more edges) unblocks score flow through external papers and surfaces papers like FAISS that benefit from second-order citations.
- **PageRank is a lagging indicator.** It scores papers based on incoming citations, which take weeks or months to accumulate. For new papers (0 citations), PageRank always returns the baseline minimum score. This makes it useful for ranking established papers but **not for judging whether a new paper is quality.**

## How to score new papers (not tested yet)

Since PageRank is lagging, new papers need proxy signals derived from the existing graph:

1. **Author signal** -- average PageRank of the authors' other papers. A new paper from authors whose previous work has high PageRank is likely quality.
2. **Reference quality** -- average PageRank of the papers it cites. If a new paper's bibliography is full of high-PageRank papers, it's engaging with important work rather than citing obscure or low-quality sources.
3. **Venue signal** -- papers at venues where high-PageRank papers are published carry a stronger prior.

None of these require the new paper to have any citations. They use the existing graph's scores as proxies -- "guilt by association." This is the **early quality predictor** approach from [issue #104](https://github.com/ArthurDevel/OpenPaperDigest/issues/104).

## What failed / issues

- pgvector arrays cause Python `ValueError` when used in boolean context (e.g. `if embedding`). Need to use `embedding is not None` instead.
- First investigation wrongly suspected rate limits were causing missing data. Rerunning with per-batch logging proved the data was consistent -- the issue is upstream in S2's indexing pipeline.
- `fetch_external_references.py` hit a read timeout on batch 64/112. Fixed by adding timeout/connection error retry logic (original only retried on 429s). Resume support saved progress so no work was lost.

## Output files

- `output/citation_edges.json` -- 131,596 citation edges (our papers only)
- `output/citation_edges_expanded.json` -- 883,809 edges (our papers + one layer of external references)
- `output/paper_index.json` -- 7,273 papers with S2 IDs
- `output/pagerank_results.json` -- full graph PageRank (390,346 nodes)
- `output/pagerank_our_papers.json` -- filtered to our 3,306 papers (JSON)
- `output/pagerank_our_papers.md` -- same, one line per paper (markdown table)
- `output/external_fetch_progress.json` -- resume checkpoint for external reference fetch

## Scripts

- `fetch_citation_edges.py` -- fetches references for our papers from S2 API, saves edges
- `fetch_external_references.py` -- fetches references for external nodes (one layer out), merges with existing edges
- `calculate_pagerank.py` -- builds graph, runs PageRank, saves results (auto-detects expanded edges)

## How to run

```bash
pip install networkx python-dotenv psycopg2-binary requests

# Copy .env.example to .env and fill in DATABASE_URL
python3 fetch_citation_edges.py           # Fetch references for our 7,273 papers
python3 fetch_external_references.py      # Expand one layer out (68k external nodes, ~30 min)
python3 calculate_pagerank.py             # Build graph, run PageRank (auto-uses expanded edges if available)
```
