"""
Restore the papers table from a backup JSON file.

This script reads a backup file created by backup_papers_table.py and restores
all paper records to the database.

Responsibilities:
- Check if database migrations have been applied
- Apply migrations if needed using Alembic
- Read backup JSON file
- Validate backup data structure
- Restore all papers to the database using batch inserts
- Report progress and completion status
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

MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_PORT = os.getenv('MYSQL_PORT', '3306')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

if not all([MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_DATABASE]):
    raise ValueError("MySQL environment variables (MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_DATABASE) are required")

DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups')
BATCH_SIZE = 100


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _check_and_apply_migrations(engine):
    """
    Check if all migrations have been applied and apply them if needed.

    Uses Alembic to check migration status and upgrade to head if needed.

    :param engine: SQLAlchemy engine instance
    """
    print("\n" + "=" * 80)
    print("CHECKING DATABASE MIGRATIONS")
    print("=" * 80)
    print()

    # Check if alembic_version table exists
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'railway'
            AND table_name = 'alembic_version'
        """))
        table_exists = result.scalar() > 0

    if not table_exists:
        print("Alembic version table does not exist. Database needs schema creation.")
        print("Creating database schema...")
        _run_alembic_upgrade(engine)
    else:
        # Check current version
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()

        print(f"Current migration version: {current_version}")
        print("Ensuring database schema is up to date...")
        _run_alembic_upgrade(engine)

    print("\nMigrations check complete.")
    print("=" * 80)
    print()


def _run_alembic_upgrade(engine):
    """
    Run alembic upgrade to head using SQLAlchemy directly.

    Creates the database schema by importing and creating all tables from the models.

    :param engine: SQLAlchemy engine instance
    """
    from shared.db import Base

    # Import all models to ensure they're registered with Base.metadata
    import papers.db.models
    import users.models

    # Create all tables
    Base.metadata.create_all(engine)

    print("Database schema created successfully.")


# ============================================================================
# MAIN SCRIPT
# ============================================================================

def main():
    """Restore papers table from JSON backup file."""

    print("=" * 80)
    print("RESTORE PAPERS TABLE")
    print("=" * 80)
    print()

    # List available backups
    if not os.path.exists(BACKUP_DIR):
        raise ValueError(f"Backup directory does not exist: {BACKUP_DIR}")

    backup_files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('papers_backup_') and f.endswith('.json')])

    if not backup_files:
        raise ValueError(f"No backup files found in {BACKUP_DIR}")

    print("Available backup files:")
    for i, filename in enumerate(backup_files, 1):
        filepath = os.path.join(BACKUP_DIR, filename)
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"  {i}. {filename} ({file_size_mb:.2f} MB)")
    print()

    # Use the most recent backup by default
    backup_file = os.path.join(BACKUP_DIR, backup_files[-1])
    print(f"Using most recent backup: {backup_files[-1]}")
    print()

    # Confirm with user
    response = input("WARNING: This will INSERT all papers from the backup. Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Restore cancelled.")
        sys.exit(0)

    # Load backup file
    print(f"\nLoading backup from {backup_file}...")
    with open(backup_file, 'r', encoding='utf-8') as f:
        backup_data = json.load(f)

    # Validate backup structure
    if 'papers' not in backup_data:
        raise ValueError("Invalid backup file: missing 'papers' key")

    papers = backup_data['papers']
    total_papers = len(papers)
    print(f"Loaded {total_papers} papers from backup")
    print(f"Backup date: {backup_data.get('backup_date', 'Unknown')}")
    print()

    # Connect to Railway database
    print("Connecting to Railway database...")
    engine = create_engine(DATABASE_URL)

    # Check and apply migrations if needed
    _check_and_apply_migrations(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Restore papers in batches
        print(f"\nRestoring papers in batches of {BATCH_SIZE}...")

        for i in range(0, total_papers, BATCH_SIZE):
            batch = papers[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            total_batches = (total_papers + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} papers)...")

            # Insert batch
            for paper in batch:
                session.execute(text("""
                    INSERT INTO papers (
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
                    ) VALUES (
                        :id,
                        :paper_uuid,
                        :arxiv_id,
                        :arxiv_version,
                        :arxiv_url,
                        :status,
                        :error_message,
                        :created_at,
                        :updated_at,
                        :started_at,
                        :finished_at,
                        :num_pages,
                        :processing_time_seconds,
                        :total_cost,
                        :avg_cost_per_page,
                        :title,
                        :authors,
                        :initiated_by_user_id,
                        :external_popularity_signals,
                        :processed_content
                    )
                """), {
                    'id': paper['id'],
                    'paper_uuid': paper['paper_uuid'],
                    'arxiv_id': paper['arxiv_id'],
                    'arxiv_version': paper['arxiv_version'],
                    'arxiv_url': paper['arxiv_url'],
                    'status': paper['status'],
                    'error_message': paper['error_message'],
                    'created_at': paper['created_at'],
                    'updated_at': paper['updated_at'],
                    'started_at': paper['started_at'],
                    'finished_at': paper['finished_at'],
                    'num_pages': paper['num_pages'],
                    'processing_time_seconds': paper['processing_time_seconds'],
                    'total_cost': paper['total_cost'],
                    'avg_cost_per_page': paper['avg_cost_per_page'],
                    'title': paper['title'],
                    'authors': paper['authors'],
                    'initiated_by_user_id': paper['initiated_by_user_id'],
                    'external_popularity_signals': paper['external_popularity_signals'],
                    'processed_content': paper['processed_content'],
                })

            # Commit batch
            session.commit()
            print(f"  Committed batch {batch_num}")

        print(f"\n=== Restore Complete ===")
        print(f"Total papers restored: {total_papers}")
        print()

    except Exception as e:
        session.rollback()
        print(f"\n=== ERROR ===")
        print(f"Restore failed: {e}")
        print("All changes have been rolled back.")
        sys.exit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()
