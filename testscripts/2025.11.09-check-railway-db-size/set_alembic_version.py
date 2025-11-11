"""
Set the alembic_version to the latest migration.

This script creates the alembic_version table and sets it to the latest migration
version so that Alembic knows the database is up to date.
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

load_dotenv()

from sqlalchemy import create_engine, text


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
LATEST_MIGRATION = "20251109_000023"


# ============================================================================
# MAIN SCRIPT
# ============================================================================

def main():
    """Set alembic_version to the latest migration."""

    print("=" * 80)
    print("SET ALEMBIC VERSION")
    print("=" * 80)
    print()

    # Connect to Railway database
    print("Connecting to Railway database...")
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Create alembic_version table if it doesn't exist
        print("Creating alembic_version table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                PRIMARY KEY (version_num)
            )
        """))
        conn.commit()

        # Check if version already exists
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        existing_version = result.scalar()

        if existing_version:
            print(f"Current version: {existing_version}")
            # Update to latest
            conn.execute(text(f"""
                UPDATE alembic_version
                SET version_num = '{LATEST_MIGRATION}'
            """))
            conn.commit()
            print(f"Updated to version: {LATEST_MIGRATION}")
        else:
            print("No existing version found.")
            # Insert latest version
            conn.execute(text(f"""
                INSERT INTO alembic_version (version_num)
                VALUES ('{LATEST_MIGRATION}')
            """))
            conn.commit()
            print(f"Set version to: {LATEST_MIGRATION}")

    print()
    print("=== Done ===")
    print("Alembic now knows the database is up to date.")


if __name__ == "__main__":
    main()
