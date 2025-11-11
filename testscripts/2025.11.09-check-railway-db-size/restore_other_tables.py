"""
Restore all tables EXCEPT papers from a backup JSON file.

This script reads a backup file created by backup_other_tables.py and restores
all table records to the database.

Responsibilities:
- Read backup JSON file
- Validate backup data structure
- Restore all tables (except papers) to the database using batch inserts
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

def _restore_table(session, table_name, rows):
    """
    Restore data to a specific table.

    Uses INSERT IGNORE to skip duplicate records.

    :param session: SQLAlchemy session instance
    :param table_name: Name of the table to restore to
    :param rows: List of dictionaries representing rows to insert
    """
    if not rows:
        print(f"  No data to restore for '{table_name}'")
        return

    # Skip alembic_version table
    if table_name == 'alembic_version':
        print(f"  Skipping '{table_name}' (managed by Alembic)")
        return

    # Get column names from first row
    columns = list(rows[0].keys())
    column_list = ', '.join(columns)
    placeholders = ', '.join([f':{col}' for col in columns])

    # Use INSERT IGNORE to skip duplicates
    insert_sql = f"""
        INSERT IGNORE INTO {table_name} ({column_list})
        VALUES ({placeholders})
    """

    # Insert in batches
    total_rows = len(rows)
    inserted = 0
    for i in range(0, total_rows, BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        for row in batch:
            result = session.execute(text(insert_sql), row)
            inserted += result.rowcount

    session.commit()
    skipped = total_rows - inserted
    if skipped > 0:
        print(f"  Restored {inserted} rows to '{table_name}' (skipped {skipped} duplicates)")
    else:
        print(f"  Restored {inserted} rows to '{table_name}'")


# ============================================================================
# MAIN SCRIPT
# ============================================================================

def main():
    """Restore other tables from JSON backup file."""

    print("=" * 80)
    print("RESTORE OTHER TABLES (EXCLUDING PAPERS)")
    print("=" * 80)
    print()

    # List available backups
    if not os.path.exists(BACKUP_DIR):
        raise ValueError(f"Backup directory does not exist: {BACKUP_DIR}")

    backup_files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('other_tables_backup_') and f.endswith('.json')])

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
    response = input("WARNING: This will INSERT all table data from the backup. Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Restore cancelled.")
        sys.exit(0)

    # Load backup file
    print(f"\nLoading backup from {backup_file}...")
    with open(backup_file, 'r', encoding='utf-8') as f:
        backup_data = json.load(f)

    # Validate backup structure
    if 'tables' not in backup_data:
        raise ValueError("Invalid backup file: missing 'tables' key")

    tables = backup_data['tables']
    print(f"Loaded backup with {len(tables)} tables")
    print(f"Backup date: {backup_data.get('backup_date', 'Unknown')}")
    print()

    # Connect to Railway database
    print("Connecting to Railway database...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Define table order based on foreign key dependencies
        # Tables without dependencies first, then tables that depend on them
        table_order = [
            'alembic_version',
            'users',
            'user_requests',
            'paper_slugs',
            'user_lists',
        ]

        # Restore tables in dependency order
        print(f"Restoring tables in dependency order...")
        print()

        # First restore tables in the defined order
        for table_name in table_order:
            if table_name in tables:
                print(f"Restoring '{table_name}'...")
                rows = tables[table_name]['rows']
                _restore_table(session, table_name, rows)

        # Then restore any remaining tables not in the order list
        for table_name, table_data in tables.items():
            if table_name not in table_order:
                print(f"Restoring '{table_name}'...")
                rows = table_data['rows']
                _restore_table(session, table_name, rows)

        print(f"\n=== Restore Complete ===")
        print(f"Total tables restored: {len(tables)}")
        print()

        # Show summary
        print("Summary:")
        for table_name, table_data in tables.items():
            print(f"  {table_name}: {table_data['row_count']} rows")

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
