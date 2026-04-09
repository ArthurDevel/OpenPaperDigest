"""
Fetch completed papers from the last 4 weeks and group them by ISO week.

Responsibilities:
- Connect to PostgreSQL and query the papers table for recent completed papers
- Use published_at as the effective date, falling back to finished_at
- Group papers by ISO week (Monday-based)
- Save grouped results to output/papers_by_week.json
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
import os

from sqlalchemy import create_engine, text


# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
OUTPUT_PATH = SCRIPT_DIR / "output" / "papers_by_week.json"

# Use a specific date range where we have rich data (60-70 papers/week)
# Override with env vars if desired
DEFAULT_START = "2025-12-15"
DEFAULT_END = "2026-01-19"


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    load_dotenv(SCRIPT_DIR / ".env")

    database_url = os.environ["DATABASE_URL"]
    # SQLAlchemy needs the psycopg2 driver prefix
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(database_url)

    start_date = os.environ.get("FETCH_START", DEFAULT_START)
    end_date = os.environ.get("FETCH_END", DEFAULT_END)

    rows = fetch_completed_papers(engine, start_date, end_date)
    weeks = group_by_week(rows)

    result = {
        "weeks": weeks,
        "total_papers": sum(w["paper_count"] for w in weeks),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, default=str))

    print(f"Total papers: {result['total_papers']}")
    for w in weeks:
        print(f"  {w['week_start']} - {w['week_end']}: {w['paper_count']} papers")
    print(f"Saved to {OUTPUT_PATH}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_completed_papers(engine, start_date, end_date):
    """Query papers table for completed papers within the given date range."""
    query = text("""
        SELECT
            id,
            paper_uuid,
            arxiv_id,
            title,
            abstract,
            published_at,
            finished_at,
            classification
        FROM papers
        WHERE status = 'completed'
          AND COALESCE(published_at, finished_at) >= :start_date
          AND COALESCE(published_at, finished_at) < :end_date
        ORDER BY COALESCE(published_at, finished_at) ASC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"start_date": start_date, "end_date": end_date})
        return [dict(row._mapping) for row in result]


def group_by_week(rows):
    """Group paper rows by ISO week based on effective date (published_at or finished_at)."""
    buckets = {}

    for row in rows:
        effective_date = row["published_at"] or row["finished_at"]
        if effective_date is None:
            continue

        # ISO calendar: Monday-based weeks
        iso = effective_date.isocalendar()
        week_key = (iso.year, iso.week)

        if week_key not in buckets:
            # Compute Monday (start) and Sunday (end) of this ISO week
            monday = datetime.strptime(f"{iso.year}-W{iso.week:02d}-1", "%G-W%V-%u").date()
            sunday = monday + timedelta(days=6)
            buckets[week_key] = {
                "week_start": monday.isoformat(),
                "week_end": sunday.isoformat(),
                "papers": [],
            }

        categories = extract_categories(row["classification"])

        buckets[week_key]["papers"].append({
            "id": row["id"],
            "paper_uuid": row["paper_uuid"],
            "arxiv_id": row["arxiv_id"],
            "title": row["title"],
            "abstract": row["abstract"],
            "published_at": effective_date.isoformat(),
            "categories": categories,
        })

    # Sort by week_start and add paper_count
    weeks = sorted(buckets.values(), key=lambda w: w["week_start"])
    for w in weeks:
        w["paper_count"] = len(w["papers"])

    return weeks


def extract_categories(classification):
    """Pull arXiv category list from the JSONB classification field."""
    if not classification:
        return []
    # classification is typically {"categories": ["cs.LG", "cs.AI"]}
    if isinstance(classification, dict):
        return classification.get("categories", [])
    return []


if __name__ == "__main__":
    main()
