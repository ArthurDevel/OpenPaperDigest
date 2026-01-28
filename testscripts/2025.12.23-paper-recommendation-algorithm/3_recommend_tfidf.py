"""
Paper Recommendation using TF-IDF

Simple keyword-based recommendation using TF-IDF vectorization.
No ML models required - just scikit-learn.

Usage:
    python 3_recommend_tfidf.py
    python 3_recommend_tfidf.py --top 20
"""

import os
import argparse
from math import exp, log
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))


# =============================================================================
# CONFIGURATION
# =============================================================================

MYSQL_HOST = "localhost"
MYSQL_PORT = "3306"
MYSQL_USER = os.getenv("MYSQL_USER", "workflow_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "workflow_db")

# Scoring parameters
DEFAULT_HALF_LIFE_DAYS = 30
H_INDEX_CAP = 100
DEFAULT_TOP_N = 10

# Weights (semantic, recency, author)
WEIGHT_SEMANTIC = 0.50
WEIGHT_RECENCY = 0.30
WEIGHT_AUTHOR = 0.20


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ScoredPaper:
    arxiv_id: str
    title: str
    abstract: Optional[str]
    published_at: Optional[datetime]
    primary_category: Optional[str]
    avg_author_h_index: Optional[float]
    semantic_score: float
    recency_score: float
    author_score: float
    total_score: float

    def __str__(self):
        h_idx = f"{self.avg_author_h_index:.1f}" if self.avg_author_h_index else "N/A"
        pub_date = self.published_at.strftime("%Y-%m-%d") if self.published_at else "N/A"
        return (
            f"[{self.total_score:.3f}] {self.arxiv_id} ({self.primary_category})\n"
            f"  Title: {self.title[:80]}{'...' if len(self.title) > 80 else ''}\n"
            f"  Published: {pub_date} | Avg H-Index: {h_idx}\n"
            f"  Scores: sem={self.semantic_score:.3f}, rec={self.recency_score:.3f}, auth={self.author_score:.3f}"
        )


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================

def compute_recency_score(published_at: Optional[datetime], half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    if published_at is None:
        return 0.0

    if published_at.tzinfo is not None:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.now()

    days_old = (now - published_at).days
    if days_old < 0:
        return 1.0

    decay_rate = 0.693147 / half_life_days
    return exp(-decay_rate * days_old)


def compute_author_score(avg_h_index: Optional[float], cap: float = H_INDEX_CAP) -> float:
    if avg_h_index is None or avg_h_index <= 0:
        return 0.0
    score = log(1 + avg_h_index) / log(1 + cap)
    return min(1.0, score)


# =============================================================================
# DATABASE
# =============================================================================

def get_database_url() -> str:
    return f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"


def load_papers() -> list[dict]:
    engine = create_engine(get_database_url())
    query = text("""
        SELECT
            arxiv_id,
            title,
            abstract,
            published_at,
            primary_category,
            avg_author_h_index
        FROM arxiv_papers
        WHERE title IS NOT NULL
    """)

    with engine.connect() as conn:
        result = conn.execute(query)
        return [dict(row._mapping) for row in result]


# =============================================================================
# TF-IDF RECOMMENDATION
# =============================================================================

def recommend_papers(
    query: str,
    top_n: int = DEFAULT_TOP_N,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    weights: tuple[float, float, float] = (WEIGHT_SEMANTIC, WEIGHT_RECENCY, WEIGHT_AUTHOR),
) -> list[ScoredPaper]:
    w_sem, w_rec, w_auth = weights

    # Load papers
    print("Loading papers from database...")
    papers = load_papers()
    print(f"Loaded {len(papers)} papers")

    if not papers:
        return []

    # Build corpus: title + abstract for each paper
    print("Building TF-IDF vectors...")
    corpus = []
    for paper in papers:
        text = paper["title"] or ""
        if paper["abstract"]:
            text += " " + paper["abstract"]
        corpus.append(text)

    # Fit TF-IDF on corpus + query
    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=10000,
        ngram_range=(1, 2),  # unigrams and bigrams
    )

    # Fit on corpus, transform corpus and query
    tfidf_matrix = vectorizer.fit_transform(corpus)
    query_vec = vectorizer.transform([query])

    # Compute similarities
    print("Computing similarities...")
    similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()

    # Score papers
    scored_papers = []
    for i, paper in enumerate(papers):
        semantic_score = float(similarities[i])
        recency_score = compute_recency_score(paper["published_at"], half_life_days)
        author_score = compute_author_score(paper["avg_author_h_index"])

        total_score = (
            w_sem * semantic_score +
            w_rec * recency_score +
            w_auth * author_score
        )

        scored_papers.append(ScoredPaper(
            arxiv_id=paper["arxiv_id"],
            title=paper["title"],
            abstract=paper["abstract"],
            published_at=paper["published_at"],
            primary_category=paper["primary_category"],
            avg_author_h_index=paper["avg_author_h_index"],
            semantic_score=semantic_score,
            recency_score=recency_score,
            author_score=author_score,
            total_score=total_score,
        ))

    scored_papers.sort(key=lambda p: p.total_score, reverse=True)
    return scored_papers[:top_n]


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Recommend papers using TF-IDF")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--half-life", type=float, default=DEFAULT_HALF_LIFE_DAYS)
    args = parser.parse_args()

    weights = (WEIGHT_SEMANTIC, WEIGHT_RECENCY, WEIGHT_AUTHOR)

    print("=" * 80)
    print("Paper Recommendation System (TF-IDF)")
    print(f"Settings: top={args.top}, half_life={args.half_life}d, weights={weights}")
    print("=" * 80)
    print()

    query = input("Enter your search query: ").strip()
    if not query:
        print("No query provided.")
        return

    print()
    results = recommend_papers(query, args.top, args.half_life, weights)

    if not results:
        print("No results found.")
        return

    print()
    print("=" * 80)
    print(f"TOP {len(results)} RESULTS")
    print("=" * 80)

    for i, paper in enumerate(results, 1):
        print(f"\n{i}. {paper}")


if __name__ == "__main__":
    main()
