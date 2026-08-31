"""Apply pending SQL migrations from db/migrations/ in filename order.

Tracks applied migrations in a `schema_migrations` table so re-running is a
no-op for files already applied. Each migration runs in its own transaction.

Usage:
    python scripts/migrate.py
"""

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def main() -> int:
    load_dotenv()
    db_url = os.environ.get("SUPABASE_DB_URL_DIRECT")
    if not db_url:
        print("SUPABASE_DB_URL_DIRECT is not set. Copy .env.example to .env and fill it in.")
        return 1

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print(f"No migration files found in {MIGRATIONS_DIR}")
        return 0

    with psycopg.connect(db_url, connect_timeout=10, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("SELECT filename FROM schema_migrations;")
            applied = {row[0] for row in cur.fetchall()}

        pending = [f for f in migration_files if f.name not in applied]
        if not pending:
            print("Nothing to apply — schema is up to date.")
            return 0

        for path in pending:
            print(f"Applying {path.name} ...")
            sql = path.read_text()
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(sql)
                        cur.execute(
                            "INSERT INTO schema_migrations (filename) VALUES (%s);",
                            (path.name,),
                        )
            except psycopg.Error as exc:
                print(f"Migration {path.name} failed: {exc}")
                return 1

    print(f"Applied {len(pending)} migration(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
