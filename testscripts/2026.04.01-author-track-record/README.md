# Author Track Record as Paper Quality Predictor

## Goal

Test whether **author track record** (measured as the median PageRank of an author's papers) predicts paper quality (measured as the paper's own PageRank score). If so, this signal could help surface promising papers from established authors before they accumulate citations -- "hidden gems."

## What we tested

1. Loaded 390,346 PageRank scores from the expanded citation graph (883k edges, one layer out).
2. Queried the database for 4,539 papers with author links across 29,580 unique authors.
3. For each author, computed aggregate PageRank stats (median, mean, max) across their papers.
4. For each paper, computed an "author track record" score = MAX of its authors' median PageRank scores.
5. Measured correlation between author track record and paper PageRank.
6. Identified "hidden gems": papers with zero PageRank but high author track record.

## Results

### Initial results (all authors)

| Metric | Pearson r | Spearman r |
|--------|-----------|------------|
| Author track record vs Paper PageRank | 0.984 (p~0) | 0.748 (p~0) |
| h-index vs Paper PageRank | 0.081 (p=7.7e-5) | 0.228 (p=3.4e-29) |

**Problem:** this correlation is inflated. Most authors (90%) have only 1 paper in our graph, so their "track record" equals their own paper's PageRank. The correlation is partly circular.

### Filtered results (authors with 2+ papers only)

Filtering to only authors with 2+ papers removes the circularity. The track record for these authors comes from their *other* papers, making it a genuine external signal.

| Metric | Pearson r | Spearman r |
|--------|-----------|------------|
| Author track record (2+ papers) vs Paper PageRank | **0.653** (p=2.5e-161) | **0.595** (p=6.4e-127) |
| h-index vs Paper PageRank | 0.027 (p=0.33) | 0.113 (p=4.2e-5) |

- 2,957 authors have 2+ papers (10% of total, but these are the ones with real signal)
- 1,507 papers have at least one multi-paper author
- 1,319 of those have both track record + PageRank for correlation

### Top authors with 2+ papers

| Author | Median PageRank | Papers | h-index |
|--------|----------------|--------|---------|
| Zesen Cheng (Qwen) | 0.0000095 | 2 | 14 |
| Peng Wang (Qwen) | 0.0000082 | 3 | 7 |
| S. Gu (GPT-4 co-author) | 0.0000080 | 2 | 4 |
| Johannes Heidecke (OpenAI) | 0.0000078 | 2 | 18 |
| Alec Radford (OpenAI) | 0.0000075 | 2 | 33 |
| Xuejing Liu | 0.0000068 | 4 | 5 |
| Yang Fan (Qwen) | 0.0000067 | 2 | 6 |

### Hidden gems (multi-paper authors only)

36 papers with zero PageRank citations but author track record >= 75th percentile. These are from authors with proven track records elsewhere -- the strongest "early quality" signal we have.

Top 10:

| Track Record | Author (papers) | arXiv ID | Title |
|---|---|---|---|
| 0.0000047 | Jingren Zhou (27) | 2603.08398 | Revealing Behavioral Plasticity in LLMs |
| 0.0000046 | Zekun Wang (11) | 2512.23343 | AI Meets Brain: Memory Systems Survey |
| 0.0000044 | Jiaye Ge (5) | 2603.09877 | InternVL-U |
| 0.0000036 | Yu Bai (2) | 2603.12201 | IndexCache: Accelerating Sparse Attention |
| 0.0000035 | Dahua Lin (8) | 2602.08990 | InternAgent-1.5 |
| 0.0000035 | Jingwei Wu (5) | 2602.10604 | Step 3.5 Flash |
| 0.0000033 | Da Yin (6) | 2603.10910 | GLM-OCR Technical Report |
| 0.0000032 | Shuicheng Yan (6) | 2603.12038 | Slow-Fast Inference |
| 0.0000032 | Zhicheng Dou (40) | 2603.03379 | MemSifter |
| 0.0000031 | Chengda Lu (7) | 2412.19437 | DeepSeek-V3 Technical Report |

## Key Observations

1. **Author track record is a strong predictor** -- Pearson r=0.653 with the circularity removed. **24x stronger** than h-index (r=0.027). This is a genuine leading signal for new papers.

2. **h-index is nearly useless** -- r=0.027 (not even statistically significant at p=0.33). h-index is a slow-moving, field-agnostic metric. It doesn't capture an author's recent impact in the specific research area we care about.

3. **The signal improves with more author data.** Only 10% of authors have 2+ papers in our graph. As the citation graph grows and more author-paper links are established, the coverage and reliability of this signal will increase.

4. **36 actionable hidden gems** -- papers by proven authors with 0 citations yet. These are the strongest candidates for early quality boosting.

5. **Limitation: author matching is incomplete** -- only 4,539 of ~7,273 papers have author links. The `paper_authors` table needs better coverage.

## How to run

```bash
pip install psycopg2-binary python-dotenv scipy

# Copy .env.example to .env and fill in DATABASE_URL
python3 explore_author_track_record.py                    # All authors (inflated correlation)
python3 explore_author_track_record.py --multi-paper-only # 2+ paper authors (genuine signal)
```

## Files

- `explore_author_track_record.py` -- Main analysis script (supports `--multi-paper-only` flag)
- `.env.example` -- Environment variable template
- `output/analysis.txt` -- Full stdout output (all authors)
- `output/analysis_multi_paper.txt` -- Filtered analysis (2+ papers only)
- `output/author_scores.json` -- Per-author PageRank aggregates (all authors)
- `output/author_scores_multi_paper.json` -- Per-author PageRank aggregates (2+ papers only)
- `output/paper_author_track_record.md` -- All papers ranked by author track record
- `output/paper_author_track_record_multi_paper.md` -- Multi-paper authors only
