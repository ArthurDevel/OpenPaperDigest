"""
Paper Recommendation Algorithm Test Script

Recommends papers based on a query using a combination of:
1. Semantic similarity (SPECTER2 embeddings via HuggingFace)
2. Recency (exponential decay)
3. Author quality (avg h-index, log normalized)

NOTE: Run 2_batch_embed_specter2.py first to embed papers with SPECTER2.

Usage:
    python 1_recommend_papers.py
    python 1_recommend_papers.py --top 20
    python 1_recommend_papers.py --half-life 14
"""

import os
import json
import argparse
from math import exp, log
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Database config - use host port for local development
# When running locally, connect to localhost with the exposed host port
MYSQL_HOST = "localhost"
MYSQL_PORT = "3306"  # Docker exposes MySQL on 3306
MYSQL_USER = os.getenv("MYSQL_USER", "workflow_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "workflow_db")

# HuggingFace token for SPECTER2 embeddings
HF_TOKEN = os.getenv("HF_TOKEN")

# SPECTER2 model config
SPECTER2_MODEL = "allenai/specter2_base"
SPECTER2_QUERY_MODEL = "allenai/specter2_adhoc_query"  # Adapter for search queries
EMBEDDING_MODEL_NAME = "specter2_base"
MAX_TEXT_CHARS = 1800  # BERT 512 token limit ≈ 1800 chars

# Scoring parameters
DEFAULT_HALF_LIFE_DAYS = 30  # Papers from 30 days ago score 0.5 on recency
H_INDEX_CAP = 100  # h-index values above this are capped at 1.0
DEFAULT_TOP_N = 10

# Weights for scoring (semantic, recency, author) - must sum to 1
WEIGHT_SEMANTIC = 0.50
WEIGHT_RECENCY = 0.30
WEIGHT_AUTHOR = 0.20


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ScoredPaper:
    """Paper with computed relevance scores."""
    arxiv_id: str
    title: str
    abstract: Optional[str]
    published_at: Optional[datetime]
    primary_category: Optional[str]
    avg_author_h_index: Optional[float]

    # Individual scores (0-1)
    semantic_score: float
    recency_score: float
    author_score: float

    # Combined score
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
# EMBEDDING FUNCTIONS
# =============================================================================

def embed_query_specter2(query: str) -> Optional[list[float]]:
    """
    Embed a query string using SPECTER2 with adhoc_query adapter (local model).

    The adhoc_query adapter is trained for search queries, making it better at
    matching casual natural language queries to scientific paper embeddings.

    Args:
        query: The search query to embed.

    Returns:
        768-dimensional embedding vector, or None if model fails.
    """
    import torch
    from transformers import AutoTokenizer
    from adapters import AutoAdapterModel

    try:
        # Load model and adapter (cached after first call)
        tokenizer = AutoTokenizer.from_pretrained(SPECTER2_MODEL)
        model = AutoAdapterModel.from_pretrained(SPECTER2_MODEL)
        model.load_adapter(SPECTER2_QUERY_MODEL, source="hf", load_as="adhoc_query", set_active=True)

        # Tokenize and embed
        inputs = tokenizer(
            query,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        )

        with torch.no_grad():
            output = model(**inputs)

        # Get [CLS] token embedding
        embedding = output.last_hidden_state[:, 0, :].squeeze().tolist()
        return embedding

    except Exception as e:
        print(f"Error embedding query: {e}")
        return None


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.array(vec1)
    b = np.array(vec2)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================

def compute_recency_score(published_at: Optional[datetime], half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    """
    Compute recency score using exponential decay.

    Args:
        published_at: Publication datetime (timezone-aware or naive).
        half_life_days: Number of days for score to decay to 0.5.

    Returns:
        Score between 0 and 1, where 1 is today and 0.5 is half_life_days ago.
    """
    if published_at is None:
        return 0.0

    # Make now timezone-aware if published_at is timezone-aware
    if published_at.tzinfo is not None:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.now()

    days_old = (now - published_at).days

    if days_old < 0:
        return 1.0  # Future date, treat as brand new

    # λ = ln(2) / half_life
    decay_rate = 0.693147 / half_life_days

    return exp(-decay_rate * days_old)


def compute_author_score(avg_h_index: Optional[float], cap: float = H_INDEX_CAP) -> float:
    """
    Compute author quality score using log normalization.

    Args:
        avg_h_index: Average h-index of paper authors.
        cap: H-index value that maps to score 1.0.

    Returns:
        Score between 0 and 1.
    """
    if avg_h_index is None or avg_h_index <= 0:
        return 0.0

    # log(1 + h) / log(1 + cap), capped at 1.0
    score = log(1 + avg_h_index) / log(1 + cap)
    return min(1.0, score)


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def get_database_url() -> str:
    """Build MySQL connection URL from environment variables."""
    return f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"


def load_papers_with_embeddings() -> list[dict]:
    """
    Load all papers from arxiv_papers that have embeddings.

    Returns:
        List of paper dicts with embedding_vector parsed from JSON.
    """
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
            # Parse embedding from JSON string
            emb = paper["embedding_vector"]

            if emb:
                if isinstance(emb, str):
                    parsed = json.loads(emb)
                    # Handle double-encoded JSON (string inside string)
                    if isinstance(parsed, str):
                        parsed = json.loads(parsed)
                    paper["embedding_vector"] = parsed
                elif isinstance(emb, list):
                    paper["embedding_vector"] = emb
                else:
                    continue

            # Skip papers without valid embeddings
            if not paper["embedding_vector"] or not isinstance(paper["embedding_vector"], list):
                continue

            papers.append(paper)

    return papers


# =============================================================================
# MAIN RECOMMENDATION FUNCTION
# =============================================================================

def recommend_papers(
    query: str,
    top_n: int = 10,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    weights: tuple[float, float, float] = (1/3, 1/3, 1/3),
) -> list[ScoredPaper]:
    """
    Recommend papers based on a query.

    Args:
        query: Search query string.
        top_n: Number of top results to return.
        half_life_days: Half-life for recency decay.
        weights: Tuple of (semantic_weight, recency_weight, author_weight).

    Returns:
        List of ScoredPaper objects, sorted by total_score descending.
    """
    w_sem, w_rec, w_auth = weights

    # Step 1: Embed the query
    print(f"Embedding query: '{query}'...")
    query_embedding = embed_query_specter2(query)
    if query_embedding is None:
        print("Failed to embed query!")
        return []
    print(f"Query embedded (dim={len(query_embedding)})")

    # Step 2: Load papers from database
    print("Loading papers from database...")
    papers = load_papers_with_embeddings()
    print(f"Loaded {len(papers)} papers with embeddings")

    if not papers:
        print("No papers found with embeddings!")
        return []

    # Step 3: Score each paper
    print("Computing scores...")
    scored_papers = []

    for paper in papers:
        # Semantic similarity
        semantic_score = cosine_similarity(query_embedding, paper["embedding_vector"])
        # Normalize from [-1, 1] to [0, 1]
        semantic_score = (semantic_score + 1) / 2

        # Recency
        recency_score = compute_recency_score(paper["published_at"], half_life_days)

        # Author quality
        author_score = compute_author_score(paper["avg_author_h_index"])

        # Combined score
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

    # Step 4: Sort by total score and return top N
    scored_papers.sort(key=lambda p: p.total_score, reverse=True)

    return scored_papers[:top_n]


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Recommend papers based on a search query",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python 1_recommend_papers.py
    python 1_recommend_papers.py --top 20
        """
    )
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help=f"Number of results (default: {DEFAULT_TOP_N})")
    parser.add_argument("--half-life", type=float, default=DEFAULT_HALF_LIFE_DAYS,
                        help=f"Recency half-life in days (default: {DEFAULT_HALF_LIFE_DAYS})")

    args = parser.parse_args()

    weights = (WEIGHT_SEMANTIC, WEIGHT_RECENCY, WEIGHT_AUTHOR)

    print("=" * 80)
    print("Paper Recommendation System (SPECTER2)")
    print(f"Paper embeddings: {SPECTER2_MODEL}")
    print(f"Query embeddings: {SPECTER2_QUERY_MODEL}")
    print(f"Settings: top={args.top}, half_life={args.half_life}d, weights={weights}")
    print("=" * 80)
    print()

    # Prompt for query
    query = input("Enter your search query: ").strip()
    if not query:
        print("No query provided. Exiting.")
        return

    print()

    results = recommend_papers(
        query=query,
        top_n=args.top,
        half_life_days=args.half_life,
        weights=weights,
    )

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
