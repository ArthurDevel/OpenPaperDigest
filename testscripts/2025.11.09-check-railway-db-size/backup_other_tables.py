"""
Backup all tables EXCEPT the papers table to a local JSON file.

This creates a backup of all other table records (users, paper_slugs, user_requests, etc.)
before running operations that might affect the database.

Responsibilities:
- Connect to the OLD Railway database
- Fetch all tables from the database
- Exclude the papers table
- Backup all other tables to JSON
- Report completion status
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

load_dotenv()

from sqlalchemy import create_engine, text, inspect
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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_table_data(session, table_name):
    """
    Get all data from a table.

    :param session: SQLAlchemy session instance
    :param table_name: Name of the table to fetch data from
    :return: List of dictionaries representing rows
    """
    result = session.execute(text(f"SELECT * FROM {table_name}"))
    columns = result.keys()

    rows = []
    for row in result.fetchall():
        row_dict = {}
        for i, col in enumerate(columns):
            value = row[i]
            # Convert datetime to ISO format string
            if hasattr(value, 'isoformat'):
                value = value.isoformat()
            row_dict[col] = value
        rows.append(row_dict)

    return rows


# ============================================================================
# MAIN SCRIPT
# ============================================================================

def main():
    """Backup all tables except papers table to JSON file."""

    print("=" * 80)
    print("BACKUP OTHER TABLES (EXCLUDING PAPERS)")
    print("=" * 80)
    print()

    # Create backup directory
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"other_tables_backup_{timestamp}.json")

    print(f"Backup will be saved to: {backup_file}")
    print()

    # Connect to OLD Railway database
    print("Connecting to OLD Railway database...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get all table names
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()

        # Exclude papers table
        tables_to_backup = [t for t in all_tables if t != 'papers']

        print(f"Found {len(all_tables)} total tables")
        print(f"Excluding 'papers' table")
        print(f"Will backup {len(tables_to_backup)} tables: {', '.join(tables_to_backup)}")
        print()

        # Backup each table
        backup_data = {
            'backup_timestamp': timestamp,
            'backup_date': datetime.now().isoformat(),
            'tables': {}
        }

        for table_name in tables_to_backup:
            print(f"Fetching data from '{table_name}'...")
            rows = _get_table_data(session, table_name)
            backup_data['tables'][table_name] = {
                'row_count': len(rows),
                'rows': rows
            }
            print(f"  Fetched {len(rows)} rows")

        # Save to JSON file
        print(f"\nSaving backup to {backup_file}...")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)

        file_size_mb = os.path.getsize(backup_file) / (1024 * 1024)
        print(f"\n=== Backup Complete ===")
        print(f"File: {backup_file}")
        print(f"Size: {file_size_mb:.2f} MB")
        print(f"Tables backed up: {len(tables_to_backup)}")
        print()

        # Show summary
        print("Summary:")
        for table_name, data in backup_data['tables'].items():
            print(f"  {table_name}: {data['row_count']} rows")

    except Exception as e:
        print(f"\n=== ERROR ===")
        print(f"Backup failed: {e}")
        sys.exit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()
