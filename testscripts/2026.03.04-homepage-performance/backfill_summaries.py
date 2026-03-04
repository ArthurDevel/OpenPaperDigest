"""
Backfills the summaries column from processed_content, one row at a time.

Extracts five_minute_summary from the processed_content JSON blob and writes
it to the new summaries column. Each row is committed individually so the DB
never holds more than one ~2MB blob in memory at a time.

Responsibilities:
- Find papers with processed_content but no summaries
- Extract five_minute_summary from each
- Update summaries column one row at a time
- Resume safely if interrupted (skips already-backfilled rows)
"""

import json
import os
import sys
import time

import psycopg2
from dotenv import load_dotenv

# ============================================================================
# CONSTANTS
# ============================================================================

WORKER_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "worker", ".env")

# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    load_dotenv(WORKER_ENV_PATH)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in worker/.env")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    conn.autocommit = True

    cur = conn.cursor()

    # Count how many rows need backfilling
    cur.execute("SELECT COUNT(*) FROM papers WHERE processed_content IS NOT NULL AND summaries IS NULL")
    total = cur.fetchone()[0]
    print(f"Papers to backfill: {total}")

    if total == 0:
        print("Nothing to do.")
        cur.close()
        conn.close()
        return

    # Fetch only IDs to avoid loading blobs into memory
    cur.execute(
        "SELECT id FROM papers "
        "WHERE processed_content IS NOT NULL AND summaries IS NULL "
        "ORDER BY id"
    )
    ids = [row[0] for row in cur.fetchall()]

    backfilled = 0
    skipped = 0

    for i, paper_id in enumerate(ids):
        # Use a separate cursor per row to keep memory low.
        # The DB only needs to hold one processed_content blob at a time.
        row_cur = conn.cursor()
        try:
            row_cur.execute("SELECT processed_content FROM papers WHERE id = %s", (paper_id,))
            row = row_cur.fetchone()

            if not row or not row[0]:
                skipped += 1
                continue

            content = json.loads(row[0])
            five_minute_summary = content.get("five_minute_summary")

            if five_minute_summary:
                summaries = json.dumps({"five_minute_summary": five_minute_summary})
                row_cur.execute(
                    "UPDATE papers SET summaries = %s WHERE id = %s",
                    (summaries, paper_id)
                )
                backfilled += 1
            else:
                skipped += 1

        except (json.JSONDecodeError, TypeError) as e:
            print(f"  [{i+1}/{total}] SKIP id={paper_id}: {e}")
            skipped += 1
        finally:
            row_cur.close()

        if (i + 1) % 10 == 0 or (i + 1) == total:
            print(f"  [{i+1}/{total}] backfilled={backfilled}, skipped={skipped}")

        # Small delay to avoid overwhelming the DB
        time.sleep(0.1)

    print(f"\nDone. Backfilled: {backfilled}, Skipped: {skipped}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
