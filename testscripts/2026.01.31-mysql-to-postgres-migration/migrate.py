"""
MySQL to PostgreSQL Data Migration Script

Migrates all data from the MySQL (Railway) database to PostgreSQL (Supabase).

Tables migrated:
- papers
- paper_slugs
- users
- user_lists
- user_requests
- paper_status_history
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pymysql
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv


# ============================================================================
# CONSTANTS
# ============================================================================

# Batch size for inserts (small to handle large text fields)
BATCH_SIZE = 10

# Columns that need MySQL int (0/1) to PostgreSQL boolean conversion
BOOLEAN_COLUMNS = {"tombstone", "is_processed"}

# Tables to migrate in order (respecting foreign key dependencies)
# Comment out tables that are already migrated
TABLES_IN_ORDER = [
    # "papers",  # DONE - 1702 rows migrated
    # "paper_slugs",  # DONE - 983 rows migrated
    "users",
    "user_lists",
    "user_requests",
    "paper_status_history",
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_mysql_url(url: str) -> dict[str, Any]:
    """
    Parse MySQL connection URL into components.

    @param url: MySQL URL in format mysql://user:pass@host:port/database
    @return: Dictionary with host, port, user, password, database
    """
    # Remove mysql:// prefix
    url = url.replace("mysql://", "")

    # Split user:pass@host:port/database
    auth_part, rest = url.split("@")
    user, password = auth_part.split(":")

    host_port, database = rest.split("/")
    host, port = host_port.split(":")

    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "database": database,
    }


def parse_postgres_url(url: str) -> dict[str, Any]:
    """
    Parse PostgreSQL connection URL into components.
    Converts pooler URL (port 6543) to direct connection (port 5432).

    @param url: PostgreSQL URL
    @return: Dictionary with connection parameters
    """
    # Remove postgresql:// prefix
    url = url.replace("postgresql://", "")

    # Handle query params
    if "?" in url:
        url, _ = url.split("?")

    # Split user:pass@host:port/database
    auth_part, rest = url.split("@")
    user, password = auth_part.split(":")

    host_port, database = rest.split("/")
    host, port = host_port.split(":")

    # Convert transaction pooler (6543) to session pooler (5432)
    # Session pooler is more stable for migrations
    if int(port) == 6543:
        port = 5432

    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "database": database,
    }


def get_mysql_connection(config: dict[str, Any]) -> pymysql.Connection:
    """
    Create MySQL connection.

    @param config: Connection configuration dictionary
    @return: MySQL connection object
    """
    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_postgres_connection(config: dict[str, Any]) -> psycopg2.extensions.connection:
    """
    Create PostgreSQL connection with SSL for Supabase.

    @param config: Connection configuration dictionary
    @return: PostgreSQL connection object
    """
    return psycopg2.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        sslmode="require",
        connect_timeout=30,
    )


def get_table_columns(pg_conn: psycopg2.extensions.connection, table_name: str) -> list[str]:
    """
    Get column names for a table from PostgreSQL.

    @param pg_conn: PostgreSQL connection
    @param table_name: Name of the table
    @return: List of column names
    """
    with pg_conn.cursor() as cursor:
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        return [row[0] for row in cursor.fetchall()]


def fetch_mysql_data(mysql_conn: pymysql.Connection, table_name: str) -> list[dict]:
    """
    Fetch all data from a MySQL table.

    @param mysql_conn: MySQL connection
    @param table_name: Name of the table
    @return: List of row dictionaries
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {table_name}")
        return cursor.fetchall()


def table_exists_mysql(mysql_conn: pymysql.Connection, table_name: str) -> bool:
    """
    Check if a table exists in MySQL.

    @param mysql_conn: MySQL connection
    @param table_name: Name of the table
    @return: True if table exists
    """
    with mysql_conn.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) as cnt
            FROM information_schema.tables
            WHERE table_schema = DATABASE() AND table_name = %s
        """, (table_name,))
        result = cursor.fetchone()
        return result["cnt"] > 0


def table_exists_postgres(pg_conn: psycopg2.extensions.connection, table_name: str) -> bool:
    """
    Check if a table exists in PostgreSQL.

    @param pg_conn: PostgreSQL connection
    @param table_name: Name of the table
    @return: True if table exists
    """
    with pg_conn.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = %s
        """, (table_name,))
        result = cursor.fetchone()
        return result[0] > 0


def clear_postgres_table(pg_conn: psycopg2.extensions.connection, table_name: str) -> None:
    """
    Clear all data from a PostgreSQL table using TRUNCATE CASCADE.

    @param pg_conn: PostgreSQL connection
    @param table_name: Name of the table
    """
    with pg_conn.cursor() as cursor:
        cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
    pg_conn.commit()


def insert_data_postgres(
    pg_config: dict[str, Any],
    table_name: str,
    columns: list[str],
    rows: list[dict],
) -> int:
    """
    Insert data into PostgreSQL table in batches, reusing connection.

    @param pg_config: PostgreSQL connection config (to allow reconnection)
    @param table_name: Name of the table
    @param columns: List of column names
    @param rows: List of row dictionaries
    @return: Number of rows inserted
    """
    import time

    if not rows:
        return 0

    # Filter columns to only those that exist in both MySQL data and PostgreSQL schema
    # Use dict.fromkeys to preserve order while removing duplicates
    available_columns = list(dict.fromkeys(col for col in columns if col in rows[0]))

    # Build INSERT query
    columns_str = ", ".join(available_columns)
    query = f"INSERT INTO {table_name} ({columns_str}) VALUES %s"

    total_inserted = 0
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    max_retries = 3

    # Single connection for all batches
    conn = get_postgres_connection(pg_config)

    try:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1

            # Prepare values for this batch
            values = []
            for row in batch:
                row_values = []
                for col in available_columns:
                    val = row.get(col)
                    # Convert MySQL tinyint (0/1) to PostgreSQL boolean
                    if col in BOOLEAN_COLUMNS and val is not None:
                        val = bool(val)
                    row_values.append(val)
                values.append(tuple(row_values))

            # Retry logic for connection drops
            for attempt in range(max_retries):
                try:
                    with conn.cursor() as cursor:
                        execute_values(cursor, query, values)
                    conn.commit()
                    print(f"    [OK] Batch {batch_num}/{total_batches} ({len(batch)} rows)")
                    break
                except psycopg2.OperationalError as e:
                    if attempt < max_retries - 1:
                        print(f"    [RETRY] Batch {batch_num} failed, reconnecting...")
                        time.sleep(2)
                        # Reconnect
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = get_postgres_connection(pg_config)
                    else:
                        print(f"    [FAIL] Batch {batch_num} failed after {max_retries} attempts")
                        raise e

            total_inserted += len(batch)

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return total_inserted


def reset_sequence(pg_conn: psycopg2.extensions.connection, table_name: str, column: str = "id") -> None:
    """
    Reset PostgreSQL sequence to max value of the id column.

    @param pg_conn: PostgreSQL connection
    @param table_name: Name of the table
    @param column: Name of the serial column
    """
    with pg_conn.cursor() as cursor:
        # Get the sequence name
        cursor.execute(f"""
            SELECT pg_get_serial_sequence('{table_name}', '{column}')
        """)
        result = cursor.fetchone()

        if result and result[0]:
            sequence_name = result[0]
            # Reset sequence to max id + 1
            cursor.execute(f"""
                SELECT setval('{sequence_name}', COALESCE((SELECT MAX({column}) FROM {table_name}), 0) + 1, false)
            """)
    pg_conn.commit()


def migrate_table(
    mysql_config: dict[str, Any],
    pg_config: dict[str, Any],
    table_name: str,
) -> tuple[int, int]:
    """
    Migrate a single table from MySQL to PostgreSQL.

    @param mysql_config: MySQL connection config
    @param pg_config: PostgreSQL connection config
    @param table_name: Name of the table
    @return: Tuple of (rows_in_mysql, rows_inserted)
    """
    # Fresh connections for each table
    mysql_conn = get_mysql_connection(mysql_config)
    pg_conn = get_postgres_connection(pg_config)

    try:
        # Check if table exists in MySQL
        if not table_exists_mysql(mysql_conn, table_name):
            print(f"  [SKIP] Table '{table_name}' does not exist in MySQL")
            return (0, 0)

        # Check if table exists in PostgreSQL
        if not table_exists_postgres(pg_conn, table_name):
            print(f"  [SKIP] Table '{table_name}' does not exist in PostgreSQL")
            return (0, 0)

        # Fetch data from MySQL
        rows = fetch_mysql_data(mysql_conn, table_name)
        mysql_count = len(rows)
        print(f"  [MySQL] Found {mysql_count} rows")

        if mysql_count == 0:
            return (0, 0)

        # Get PostgreSQL columns
        pg_columns = get_table_columns(pg_conn, table_name)

        # Clear PostgreSQL table
        print(f"  [PostgreSQL] Clearing existing data...")
        clear_postgres_table(pg_conn, table_name)
        pg_conn.close()

        # Insert data (uses fresh connections per batch)
        print(f"  [PostgreSQL] Inserting {mysql_count} rows...")
        inserted = insert_data_postgres(pg_config, table_name, pg_columns, rows)

        # Reset sequence for tables with auto-increment id
        if "id" in pg_columns and table_name != "users":
            pg_conn = get_postgres_connection(pg_config)
            reset_sequence(pg_conn, table_name, "id")
            pg_conn.close()
            print(f"  [PostgreSQL] Reset sequence for '{table_name}'")

        return (mysql_count, inserted)

    finally:
        try:
            mysql_conn.close()
        except Exception:
            pass
        try:
            pg_conn.close()
        except Exception:
            pass


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main() -> None:
    """Main migration function."""
    print("=" * 60)
    print("MySQL to PostgreSQL Migration")
    print("=" * 60)
    print()

    # Load environment variables
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.normpath(os.path.join(script_dir, "../../web/.env.local"))
    print(f"Loading env from: {env_path}")

    if not os.path.exists(env_path):
        print(f"[ERROR] .env.local file not found at: {env_path}")
        sys.exit(1)

    load_dotenv(env_path)

    mysql_url = os.getenv("MYSQL_DATABASE_URL")
    postgres_url = os.getenv("DATABASE_URL")

    if not mysql_url:
        print("[ERROR] MYSQL_DATABASE_URL not found in .env.local")
        print("Make sure MYSQL_DATABASE_URL is set in web/.env.local")
        sys.exit(1)

    if not postgres_url:
        print("[ERROR] DATABASE_URL not found in environment")
        sys.exit(1)

    # Parse connection URLs
    mysql_config = parse_mysql_url(mysql_url)
    postgres_config = parse_postgres_url(postgres_url)

    print(f"MySQL: {mysql_config['host']}:{mysql_config['port']}/{mysql_config['database']}")
    print(f"PostgreSQL: {postgres_config['host']}:{postgres_config['port']}/{postgres_config['database']}")
    print()

    # Test connections
    print("Testing database connections...")
    test_mysql = get_mysql_connection(mysql_config)
    test_mysql.close()
    test_pg = get_postgres_connection(postgres_config)
    test_pg.close()
    print("Connected successfully!")
    print()

    # Migration summary
    summary = []

    try:
        for table_name in TABLES_IN_ORDER:
            print(f"[{table_name}]")
            mysql_count, inserted_count = migrate_table(mysql_config, postgres_config, table_name)
            summary.append((table_name, mysql_count, inserted_count))
            print()

        # Print summary
        print("=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"{'Table':<25} {'MySQL Rows':<15} {'Inserted':<15}")
        print("-" * 55)

        total_mysql = 0
        total_inserted = 0

        for table_name, mysql_count, inserted_count in summary:
            print(f"{table_name:<25} {mysql_count:<15} {inserted_count:<15}")
            total_mysql += mysql_count
            total_inserted += inserted_count

        print("-" * 55)
        print(f"{'TOTAL':<25} {total_mysql:<15} {total_inserted:<15}")
        print()
        print("Migration completed successfully!")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        raise


if __name__ == "__main__":
    main()
