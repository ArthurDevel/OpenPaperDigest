# Autoresearch Hackathon

Automated detection and optimization of research frontiers from our paper corpus.

## What We Built

Two systems that work together:

### 1. Research Frontiers Detection (`research-frontiers-detection/`)

A pipeline that automatically discovers research themes from our ingested papers and tracks how they evolve week over week.

- **Step 01**: Fetch papers from DB, group by ISO week
- **Step 02**: LLM assigns each paper to 1-2 themes (bootstraps taxonomy on first week, incremental after)
- **Step 03**: Data-driven trend analysis -- velocity, status (emerging/accelerating/stable/decelerating/dormant)
- **Step 04**: Seed results into Supabase for the `/frontiers` page

The LLM only does classification. All quantitative signals (velocity, dormancy, rank) come from the data.

### 2. Autoresearch Loop for Theme Quality (`theme-scoring/`)

A Karpathy-style optimization loop that improves the theme detection prompt itself.

- **Metric**: Embedding discrimination score `S = mean_intra / mean_inter` -- measures how coherent themes are internally vs how distinct they are from each other
- **Loop**: Mutate the prompt -> re-run theme detection -> score -> keep if improved, revert if not
- **Output**: HTML report showing score evolution across iterations

### 3. Frontend (`/frontiers` page)

Interactive bump chart showing theme rankings over time. Per-segment coloring based on rank change (green = rising, red = declining). Click any data point to see the papers for that theme/week.

## How to Run

```bash
# 1. Detect themes and seed DB
cd research-frontiers-detection
cp .env.example .env  # fill in DATABASE_URL + OPENROUTER_API_KEY
python run_all.py
python 04_seed_db.py

# 2. Run the optimization loop
cd ../theme-scoring
cp .env.example .env  # fill in DATABASE_URL + OPENROUTER_API_KEY
python 01_fetch_embeddings.py
python 03_autoresearch_loop.py
python 04_generate_report.py
```

## The Autoresearch Angle

The system doesn't just detect research frontiers -- it uses autoresearch to optimize its own detection methodology. The Karpathy Loop is applied to the theme detection prompt: one file (the prompt), one metric (embedding discrimination score), iterate until quality improves.
