# Theme Scoring via Embedding Discrimination

## Goal

Test whether we can objectively score the quality of LLM-generated research themes using paper embeddings. This score will be the metric for the autoresearch optimization loop.

## Approach

Score formula: `S = mean_intra / mean_inter`

- `mean_intra`: average cosine similarity between papers within the same theme (coherence)
- `mean_inter`: average cosine similarity between papers in different themes (overlap)
- Higher score = themes are internally coherent AND distinct from each other

## How to Run

```bash
cp .env.example .env
# Fill in DATABASE_URL
python 01_fetch_embeddings.py  # ~2 seconds, fetches from DB
python 02_score_themes.py      # ~1 second, pure numpy
```

## Results

Baseline score (from the frontiers detection prototype's theme assignments):

- **Score: 1.32** (mean_intra=0.47, mean_inter=0.36)
- 23 themes scored (5 filtered out for having <2 papers)
- 320 papers with embeddings

### Per-theme coherence:
- Most coherent: Recommender Systems with LLMs (0.60)
- Least coherent: Computational Physics & Cosmology (0.31) — flagged as weak
- Big themes (100+ papers) naturally score lower coherence (~0.46)

### Interpretation
- Score of 1.0 = themes are no better than random grouping
- Score of 1.32 = 32% better than random — decent but room for improvement
- The autoresearch loop should try to push this higher by optimizing the theme detection prompt
