"""
Check Railway database for papers with large processed_content.

This script connects to the Railway MySQL database and finds papers
with the largest processed_content to understand what's taking up space.
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# ============================================================================
# CONFIGURATION
# ============================================================================

RAILWAY_DATABASE_URL = ""

if not RAILWAY_DATABASE_URL:
    print("ERROR: RAILWAY_DATABASE_URL not found in environment")
    print("Please add it to your .env file")
    sys.exit(1)


# ============================================================================
# MAIN SCRIPT
# ============================================================================

def main():
    """Check papers table for large processed_content entries."""

    # Step 1: Connect to Railway database
    print(f"Connecting to Railway database...")
    engine = create_engine(RAILWAY_DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Step 2: Get table size info
        print("\n=== Table Size Information ===")
        result = session.execute(text("""
            SELECT
                TABLE_NAME as table_name,
                ROUND(((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024), 2) AS size_mb,
                TABLE_ROWS as table_rows
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = 'railway'
            ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC
        """))

        rows = result.fetchall()
        if not rows:
            print("No tables found")
        else:
            for row in rows:
                print(f"{row[0]}: {row[1]} MB ({row[2]} rows)")

        # Step 2b: Check actual data file sizes
        print("\n=== Data File Sizes (InnoDB) ===")
        result = session.execute(text("""
            SELECT
                FILE_NAME,
                ROUND(TOTAL_EXTENTS * EXTENT_SIZE / 1024 / 1024, 2) as size_mb
            FROM information_schema.FILES
            WHERE FILE_NAME LIKE '%railway%'
            ORDER BY size_mb DESC
        """))

        file_rows = result.fetchall()
        if file_rows:
            total_file_size = 0
            for row in file_rows:
                print(f"{row[0]}: {row[1]} MB")
                total_file_size += row[1] if row[1] else 0
            print(f"\nTotal data file size: {total_file_size:.2f} MB")
        else:
            print("No file information available")

        # Step 3: Get papers count by status
        print("\n=== Papers Count by Status ===")
        result = session.execute(text("""
            SELECT status, COUNT(*) as count
            FROM papers
            GROUP BY status
            ORDER BY count DESC
        """))

        for row in result.fetchall():
            print(f"{row[0]}: {row[1]}")

        # Step 4: Find papers with largest processed_content
        print("\n=== Top 20 Papers by processed_content Size ===")
        result = session.execute(text("""
            SELECT
                id,
                paper_uuid,
                arxiv_id,
                title,
                status,
                num_pages,
                LENGTH(processed_content) as content_size_bytes,
                ROUND(LENGTH(processed_content) / 1024 / 1024, 2) as content_size_mb
            FROM papers
            WHERE processed_content IS NOT NULL
            ORDER BY content_size_bytes DESC
            LIMIT 20
        """))

        print(f"{'ID':<6} {'Status':<12} {'Pages':<6} {'Size (MB)':<10} {'ArXiv ID':<15} {'Title'[:40]}")
        print("-" * 100)

        for row in result.fetchall():
            title = row[3][:40] if row[3] else "N/A"
            arxiv_id = row[2] if row[2] else "N/A"
            pages = row[5] if row[5] else 0
            print(f"{row[0]:<6} {row[4]:<12} {pages:<6} {row[7]:<10} {arxiv_id:<15} {title}")

        # Step 5: Get total size of processed_content column
        print("\n=== Total processed_content Size ===")
        result = session.execute(text("""
            SELECT
                COUNT(*) as total_papers,
                COUNT(processed_content) as papers_with_content,
                ROUND(SUM(LENGTH(processed_content)) / 1024 / 1024, 2) as total_content_mb
            FROM papers
        """))

        row = result.fetchone()
        print(f"Total papers: {row[0]}")
        print(f"Papers with processed_content: {row[1]}")
        print(f"Total processed_content size: {row[2]} MB")

        # Step 6: Check failed papers
        print("\n=== Failed Papers Info ===")
        result = session.execute(text("""
            SELECT COUNT(*) as failed_count
            FROM papers
            WHERE status = 'failed'
        """))

        failed_count = result.scalar()
        print(f"Total failed papers: {failed_count}")

        if failed_count > 0:
            print("\nSample failed papers (first 10):")
            result = session.execute(text("""
                SELECT
                    id,
                    arxiv_id,
                    error_message,
                    LENGTH(processed_content) as content_size
                FROM papers
                WHERE status = 'failed'
                LIMIT 10
            """))

            for row in result.fetchall():
                arxiv_id = row[1] if row[1] else "N/A"
                content_size = row[3] if row[3] else 0
                error = row[2][:50] if row[2] else "No error message"
                print(f"  ID {row[0]} ({arxiv_id}): {error}... (content: {content_size} bytes)")

    finally:
        session.close()
        print("\n=== Done ===")


if __name__ == "__main__":
    main()
