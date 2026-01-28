"""
Similar Paper Recommendation

Given a paper ID, find similar papers using SPECTER2 vector similarity.
No query embedding needed - uses the paper's existing embedding.

Usage:
    python 5_recommend_similar.py
"""

import os
import json
from math import exp, log
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


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

EMBEDDING_MODEL_NAME = "specter2_base"

# Scoring parameters
DEFAULT_HALF_LIFE_DAYS = 30
H_INDEX_CAP = 100
DEFAULT_TOP_N = 10

# Weights (semantic, recency, author)
WEIGHT_SEMANTIC = 0.70
WEIGHT_RECENCY = 0.20
WEIGHT_AUTHOR = 0.10


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
            f"  Scores: sim={self.semantic_score:.3f}, rec={self.recency_score:.3f}, auth={self.author_score:.3f}"
        )


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    a = np.array(vec1)
    b = np.array(vec2)
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


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


def parse_embedding(emb) -> Optional[list[float]]:
    """Parse embedding from various formats."""
    if emb is None:
        return None
    if isinstance(emb, list):
        return emb
    if isinstance(emb, str):
        parsed = json.loads(emb)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        return parsed
    return None


def get_paper_by_id(arxiv_id: str) -> Optional[dict]:
    """Fetch a single paper by arxiv_id."""
    engine = create_engine(get_database_url())
    query = text("""
        SELECT
            arxiv_id,
            title,
            abstract,
            published_at,
            primary_category,
            avg_author_h_index,
            embedding_vector
        FROM arxiv_papers
        WHERE arxiv_id = :arxiv_id
          AND embedding_vector IS NOT NULL
          AND embedding_model = :model_name
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"arxiv_id": arxiv_id, "model_name": EMBEDDING_MODEL_NAME})
        row = result.fetchone()
        if row:
            paper = dict(row._mapping)
            paper["embedding_vector"] = parse_embedding(paper["embedding_vector"])
            return paper
    return None


def load_all_papers() -> list[dict]:
    """Load all papers with embeddings."""
    engine = create_engine(get_database_url())
    query = text("""
        SELECT
            arxiv_id,
            title,
            abstract,
            published_at,
            primary_category,
            avg_author_h_index,
            embedding_vector
        FROM arxiv_papers
        WHERE embedding_vector IS NOT NULL
          AND embedding_model = :model_name
    """)

    papers = []
    with engine.connect() as conn:
        result = conn.execute(query, {"model_name": EMBEDDING_MODEL_NAME})
        for row in result:
            paper = dict(row._mapping)
            paper["embedding_vector"] = parse_embedding(paper["embedding_vector"])
            if paper["embedding_vector"]:
                papers.append(paper)

    return papers


# =============================================================================
# RECOMMENDATION
# =============================================================================

def recommend_similar(
    arxiv_id: str,
    top_n: int = DEFAULT_TOP_N,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    weights: tuple[float, float, float] = (WEIGHT_SEMANTIC, WEIGHT_RECENCY, WEIGHT_AUTHOR),
) -> tuple[Optional[dict], list[ScoredPaper]]:
    w_sem, w_rec, w_auth = weights

    # Get source paper
    print(f"Fetching paper {arxiv_id}...")
    source_paper = get_paper_by_id(arxiv_id)
    if not source_paper:
        print(f"Paper {arxiv_id} not found or has no embedding!")
        return None, []

    print(f"Source: {source_paper['title'][:60]}...")
    source_embedding = source_paper["embedding_vector"]

    # Load all papers
    print("Loading papers from database...")
    papers = load_all_papers()
    print(f"Loaded {len(papers)} papers with embeddings")

    # Score papers
    print("Computing similarities...")
    scored_papers = []

    for paper in papers:
        # Skip the source paper itself
        if paper["arxiv_id"] == arxiv_id:
            continue

        # Cosine similarity
        similarity = cosine_similarity(source_embedding, paper["embedding_vector"])
        # Normalize from [-1, 1] to [0, 1]
        semantic_score = (similarity + 1) / 2

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
    return source_paper, scored_papers[:top_n]


# =============================================================================
# CLI
# =============================================================================

def main():
    weights = (WEIGHT_SEMANTIC, WEIGHT_RECENCY, WEIGHT_AUTHOR)

    print("=" * 80)
    print("Similar Paper Recommendation (SPECTER2 Vector Search)")
    print(f"Settings: top={DEFAULT_TOP_N}, half_life={DEFAULT_HALF_LIFE_DAYS}d, weights={weights}")
    print("=" * 80)
    print()

    arxiv_id = input("Enter arXiv paper ID (e.g., 2512.16083): ").strip()
    if not arxiv_id:
        print("No paper ID provided.")
        return

    print()
    source_paper, results = recommend_similar(arxiv_id, DEFAULT_TOP_N, DEFAULT_HALF_LIFE_DAYS, weights)

    if not source_paper:
        return

    print()
    print("=" * 80)
    print(f"SOURCE PAPER: {source_paper['arxiv_id']}")
    print(f"  {source_paper['title']}")
    print("=" * 80)
    print(f"\nTOP {len(results)} SIMILAR PAPERS:")

    for i, paper in enumerate(results, 1):
        print(f"\n{i}. {paper}")


if __name__ == "__main__":
    main()
