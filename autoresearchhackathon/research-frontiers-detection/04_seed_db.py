"""
Seed the autoresearchhackathon DB tables from the pipeline JSON output.

Reads theme_assignments.json (step 02 output) and inserts into:
- autoresearchhackathon_research_themes (theme registry)
- autoresearchhackathon_paper_themes (paper-theme assignments per week)

Responsibilities:
- Read theme_assignments.json
- Look up paper IDs by arxiv_id in the papers table
- Insert themes into autoresearchhackathon_research_themes
- Insert paper-theme assignments into autoresearchhackathon_paper_themes
- Skip duplicates on re-run (idempotent)
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
INPUT_PATH = SCRIPT_DIR / "output" / "theme_assignments.json"


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    load_dotenv(SCRIPT_DIR / ".env")

    database_url = os.environ["DATABASE_URL"]
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(database_url)

    data = json.loads(INPUT_PATH.read_text())
    themes_registry = data["themes"]  # {name: {description, first_seen_week}}
    weekly_assignments = data["weekly_assignments"]  # {week: [{arxiv_id, title, themes}]}

    with engine.begin() as conn:
        # Step 1: Insert themes
        theme_id_map = insert_themes(conn, themes_registry)
        print(f"Inserted/found {len(theme_id_map)} themes")

        # Step 2: Build arxiv_id -> paper.id lookup
        all_arxiv_ids = set()
        for assignments in weekly_assignments.values():
            for a in assignments:
                if a.get("arxiv_id"):
                    all_arxiv_ids.add(a["arxiv_id"])

        paper_id_map = lookup_paper_ids(conn, all_arxiv_ids)
        print(f"Found {len(paper_id_map)}/{len(all_arxiv_ids)} papers in DB")

        # Step 3: Insert paper-theme assignments
        inserted = insert_assignments(conn, weekly_assignments, theme_id_map, paper_id_map)
        print(f"Inserted {inserted} paper-theme assignments")

    print("Done!")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def insert_themes(conn, themes_registry):
    """
    Insert themes into autoresearchhackathon_research_themes, skipping duplicates.

    Args:
        conn: SQLAlchemy connection (inside transaction)
        themes_registry: {name: {description, first_seen_week}}

    Returns:
        dict mapping theme name -> theme id
    """
    theme_id_map = {}

    for name, info in themes_registry.items():
        description = info.get("description", "")

        # Upsert: insert if not exists, otherwise get existing id
        result = conn.execute(
            text("""
                INSERT INTO autoresearchhackathon_research_themes (name, description)
                VALUES (:name, :description)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """),
            {"name": name, "description": description},
        )
        theme_id_map[name] = result.scalar_one()

    return theme_id_map


def lookup_paper_ids(conn, arxiv_ids):
    """
    Look up paper IDs by arxiv_id.

    Args:
        conn: SQLAlchemy connection
        arxiv_ids: set of arxiv_id strings

    Returns:
        dict mapping arxiv_id -> paper.id
    """
    if not arxiv_ids:
        return {}

    result = conn.execute(
        text("SELECT id, arxiv_id FROM papers WHERE arxiv_id = ANY(:ids)"),
        {"ids": list(arxiv_ids)},
    )

    return {row.arxiv_id: row.id for row in result}


def insert_assignments(conn, weekly_assignments, theme_id_map, paper_id_map):
    """
    Insert paper-theme assignments into autoresearchhackathon_paper_themes.
    Clears existing data first for idempotency, then batch-inserts.

    Args:
        conn: SQLAlchemy connection (inside transaction)
        weekly_assignments: {week: [{arxiv_id, title, themes}]}
        theme_id_map: {theme_name: theme_id}
        paper_id_map: {arxiv_id: paper_id}

    Returns:
        Number of rows inserted
    """
    # Clear existing assignments for a clean re-run
    conn.execute(text("DELETE FROM autoresearchhackathon_paper_themes"))

    rows = []
    skipped_no_paper = 0
    skipped_no_theme = 0

    for week, assignments in weekly_assignments.items():
        for a in assignments:
            arxiv_id = a.get("arxiv_id", "")
            paper_id = paper_id_map.get(arxiv_id)
            if not paper_id:
                skipped_no_paper += 1
                continue

            for theme_name in a.get("themes", []):
                theme_id = theme_id_map.get(theme_name)
                if not theme_id:
                    skipped_no_theme += 1
                    continue

                rows.append({"paper_id": paper_id, "theme_id": theme_id, "week": week})

    # Batch insert
    if rows:
        conn.execute(
            text("""
                INSERT INTO autoresearchhackathon_paper_themes (paper_id, theme_id, week)
                VALUES (:paper_id, :theme_id, :week)
            """),
            rows,
        )

    if skipped_no_paper > 0:
        print(f"  Skipped {skipped_no_paper} assignments (paper not found in DB)")
    if skipped_no_theme > 0:
        print(f"  Skipped {skipped_no_theme} assignments (theme not found)")

    return len(rows)


if __name__ == "__main__":
    main()
