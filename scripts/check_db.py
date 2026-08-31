"""Verify connectivity to the Supabase Postgres instance and print its version.

Usage:
    python scripts/check_db.py

Reads SUPABASE_DB_URL_DIRECT from the environment (or .env). This is a one-off
connectivity check for M0 — the pipeline and API each get their own connection
handling later (direct connection for ingestion, pooled for the API; see
IMPLEMENTATION_PLAN.md Risk R7).
"""

import os
import sys

import psycopg
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    db_url = os.environ.get("SUPABASE_DB_URL_DIRECT")
    if not db_url:
        print("SUPABASE_DB_URL_DIRECT is not set. Copy .env.example to .env and fill it in.")
        return 1

    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                (version,) = cur.fetchone()
                print(f"Connected. Postgres server version:\n  {version}")
    except psycopg.OperationalError as exc:
        print(f"Connection failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
