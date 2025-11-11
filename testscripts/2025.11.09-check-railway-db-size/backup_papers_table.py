"""
Backup the papers table to a local JSON file.

This creates a backup of all paper records before running OPTIMIZE TABLE.
"""

import os
import sys
import json
from datetime import datetime
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
BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups')


# ============================================================================
# MAIN SCRIPT
# ============================================================================

def main():
    """Backup papers table to JSON file."""

    print("=" * 80)
    print("BACKUP PAPERS TABLE")
    print("=" * 80)
    print()

    # Create backup directory
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"papers_backup_{timestamp}.json")

    print(f"Backup will be saved to: {backup_file}")
    print()

    # Connect to Railway database
    print("Connecting to Railway database...")
    engine = create_engine(RAILWAY_DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get all papers including processed_content
        print("\nFetching papers from database...")
        print("(including processed_content column - this may take a while)")

        result = session.execute(text("""
            SELECT
                id,
                paper_uuid,
                arxiv_id,
                arxiv_version,
                arxiv_url,
                status,
                error_message,
                created_at,
                updated_at,
                started_at,
                finished_at,
                num_pages,
                processing_time_seconds,
                total_cost,
                avg_cost_per_page,
                title,
                authors,
                initiated_by_user_id,
                external_popularity_signals,
                processed_content
            FROM papers
            ORDER BY id
        """))

        papers = []
        for row in result.fetchall():
            paper = {
                'id': row[0],
                'paper_uuid': row[1],
                'arxiv_id': row[2],
                'arxiv_version': row[3],
                'arxiv_url': row[4],
                'status': row[5],
                'error_message': row[6],
                'created_at': row[7].isoformat() if row[7] else None,
                'updated_at': row[8].isoformat() if row[8] else None,
                'started_at': row[9].isoformat() if row[9] else None,
                'finished_at': row[10].isoformat() if row[10] else None,
                'num_pages': row[11],
                'processing_time_seconds': row[12],
                'total_cost': row[13],
                'avg_cost_per_page': row[14],
                'title': row[15],
                'authors': row[16],
                'initiated_by_user_id': row[17],
                'external_popularity_signals': row[18],
                'processed_content': row[19],
            }
            papers.append(paper)

        print(f"Fetched {len(papers)} papers from database")

        # Save to JSON file
        print(f"\nSaving backup to {backup_file}...")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump({
                'backup_timestamp': timestamp,
                'backup_date': datetime.now().isoformat(),
                'total_papers': len(papers),
                'papers': papers
            }, f, indent=2, ensure_ascii=False)

        file_size_mb = os.path.getsize(backup_file) / (1024 * 1024)
        print(f"\n=== Backup Complete ===")
        print(f"File: {backup_file}")
        print(f"Size: {file_size_mb:.2f} MB")
        print(f"Papers: {len(papers)}")
        print()
        print("Backup includes all columns including processed_content.")

    except Exception as e:
        print(f"\n=== ERROR ===")
        print(f"Backup failed: {e}")
        sys.exit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()
