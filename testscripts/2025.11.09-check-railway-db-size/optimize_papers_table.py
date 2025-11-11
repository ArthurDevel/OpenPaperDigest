"""
Optimize the papers table to reclaim wasted disk space.

WARNING: This operation requires temporary disk space during the rebuild.
It may fail if there isn't enough space on Railway.
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


# ============================================================================
# MAIN SCRIPT
# ============================================================================

def main():
    """Optimize papers table to reclaim wasted space."""

    print("=" * 80)
    print("OPTIMIZE TABLE papers - Space Reclamation")
    print("=" * 80)
    print()
    print("This will rebuild the papers table to reclaim ~3 GB of wasted space.")
    print("The table currently has 3.7 GB on disk but only 575 MB of actual data.")
    print()
    print("WARNING: This operation may take several minutes and requires temporary")
    print("disk space during the rebuild. It might fail if Railway runs out of space.")
    print()

    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Aborted.")
        return

    # Connect to Railway database
    print("\nConnecting to Railway database...")
    engine = create_engine(RAILWAY_DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("\nRunning OPTIMIZE TABLE papers...")
        print("This may take several minutes. Please wait...")
        print()

        # Run OPTIMIZE TABLE
        result = session.execute(text("OPTIMIZE TABLE papers"))

        print("\n=== OPTIMIZE TABLE Results ===")
        for row in result.fetchall():
            print(f"Table: {row[0]}")
            print(f"Op: {row[1]}")
            print(f"Msg_type: {row[2]}")
            print(f"Msg_text: {row[3]}")

        # Check new file size
        print("\n=== Checking New File Size ===")
        result = session.execute(text("""
            SELECT
                FILE_NAME,
                ROUND(TOTAL_EXTENTS * EXTENT_SIZE / 1024 / 1024, 2) as size_mb
            FROM information_schema.FILES
            WHERE FILE_NAME = './railway/papers.ibd'
        """))

        row = result.fetchone()
        if row:
            print(f"New papers.ibd size: {row[1]} MB")
            print(f"Expected size: ~575 MB")
            print(f"Space reclaimed: ~{3760 - row[1]:.2f} MB")

        print("\n=== Success! ===")
        print("The table has been optimized and space has been reclaimed.")
        print("You should now have enough space to run the migration.")

    except Exception as e:
        print(f"\n=== ERROR ===")
        print(f"Optimization failed: {e}")
        print()
        print("This likely means Railway ran out of disk space during the rebuild.")
        print("You may need to temporarily upgrade Railway storage to complete this.")

    finally:
        session.close()


if __name__ == "__main__":
    main()
