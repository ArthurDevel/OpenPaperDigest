"""
Fetch paper embeddings from the database for all papers in theme_assignments.json.

Responsibilities:
- Read theme_assignments.json from the previous test script to collect arxiv_ids
- Query the papers table for embeddings (pgvector vector(1536))
- Save embeddings to output/embeddings.json
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
THEME_ASSIGNMENTS_PATH = SCRIPT_DIR / ".." / "2026.04.09-research-frontiers-detection" / "output" / "theme_assignments.json"
OUTPUT_PATH = SCRIPT_DIR / "output" / "embeddings.json"


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    load_dotenv(SCRIPT_DIR / ".env")

    database_url = os.environ["DATABASE_URL"]
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(database_url)

    # Collect all unique arxiv_ids from weekly_assignments
    arxiv_ids = collect_arxiv_ids(THEME_ASSIGNMENTS_PATH)
    print(f"Total papers in theme_assignments: {len(arxiv_ids)}")

    # Fetch embeddings from DB
    embeddings = fetch_embeddings(engine, arxiv_ids)

    missing = len(arxiv_ids) - len(embeddings)
    print(f"Papers with embeddings: {len(embeddings)}")
    print(f"Papers missing embeddings: {missing}")

    # Save
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(embeddings, indent=2))
    print(f"Saved to {OUTPUT_PATH}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def collect_arxiv_ids(path):
    """Read theme_assignments.json and return a sorted list of unique arxiv_ids."""
    data = json.loads(Path(path).read_text())
    weekly_assignments = data["weekly_assignments"]

    ids = set()
    for papers in weekly_assignments.values():
        for paper in papers:
            ids.add(paper["arxiv_id"])

    return sorted(ids)


def fetch_embeddings(engine, arxiv_ids):
    """
    Query embeddings for the given arxiv_ids.

    Returns dict of {arxiv_id: [float, ...]} for papers that have embeddings.
    """
    if not arxiv_ids:
        return {}

    query = text("""
        SELECT arxiv_id, embedding
        FROM papers
        WHERE arxiv_id = ANY(:arxiv_ids)
          AND embedding IS NOT NULL
    """)

    embeddings = {}
    with engine.connect() as conn:
        result = conn.execute(query, {"arxiv_ids": arxiv_ids})
        for row in result:
            mapping = row._mapping
            arxiv_id = mapping["arxiv_id"]
            raw = mapping["embedding"]
            embeddings[arxiv_id] = parse_embedding(raw)

    return embeddings


def parse_embedding(raw):
    """
    Parse a pgvector embedding into a list of floats.

    pgvector can return either a string like "[0.1,0.2,...]" or already a list.
    """
    if isinstance(raw, list):
        return [float(v) for v in raw]
    if isinstance(raw, str):
        return json.loads(raw)
    raise ValueError(f"Unexpected embedding type: {type(raw)}")


if __name__ == "__main__":
    main()
