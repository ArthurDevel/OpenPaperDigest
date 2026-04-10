# Research Frontiers Detection

## Goal

Test whether we can automatically detect emerging, accelerating, and declining research themes from our paper corpus using LLM-based classification + data-driven trend analysis.

## Approach

Three-step pipeline:

1. **01_fetch_papers.py** — Fetch completed papers from the DB, grouped by ISO week
2. **02_detect_themes.py** — LLM assigns each paper to 1-2 themes (bootstrap first week, incremental after)
3. **03_compute_trends.py** — Pure data analysis: compute velocity, status (emerging/accelerating/stable/decelerating/dormant), weekly sparklines

Key design principle: the LLM only classifies papers into themes. All quantitative analysis (velocity, dormancy, trend status) is data-driven.

## What We Tried

### Attempt 1: Last 4 calendar weeks
Only 7 papers in 1 week — the recent data is too sparse (gap from Jan to Mar 2026). Not enough for meaningful themes.

### Attempt 2: Dec 15 2025 – Jan 19 2026 (5 weeks, 326 papers)
Rich data period with 58-72 papers/week. This worked well.

## Results

- **28 themes** detected across 326 papers over 5 weeks
- **$0.02 total LLM cost** (google/gemini-2.5-flash via OpenRouter)
- **81,717 tokens** total

### Theme breakdown:
| Status | Count | Example |
|---|---|---|
| Emerging | 3 | AI for Scientific Discovery (+700%) |
| Accelerating | 4 | Dynamic Routing & Adaptive Networks (+500%) |
| Stable | 10 | LLM Agents for Complex Reasoning (113 papers) |
| Decelerating | 2 | Video Editing & Manipulation (-38.5%) |
| Dormant | 9 | Physics Beyond Standard Model (8→0 papers) |

### Observations
- Theme granularity is good: specific enough to be meaningful ("Reinforcement Learning & Reward Design") without being too narrow
- The LLM created 23 themes in week 1, then only 5 more across 4 subsequent weeks — taxonomy is stable
- Velocity metric correctly identifies themes that are growing vs shrinking
- Some "dormant" themes are just small (1 paper total) — could filter these out

## How to Run

```bash
cp .env.example .env
# Fill in DATABASE_URL and OPENROUTER_API_KEY
python run_all.py
```

Or run steps individually:
```bash
python 01_fetch_papers.py  # ~2 seconds
python 02_detect_themes.py # ~30 seconds, costs ~$0.02
python 03_compute_trends.py # instant
```

## Output Files

- `output/papers_by_week.json` — Raw papers grouped by week
- `output/theme_assignments.json` — Theme registry + per-week paper-theme assignments
- `output/research_frontiers.json` — Final computed trends with velocity and status
