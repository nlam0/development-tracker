"""Drop every application table and re-run migrations from scratch.

DESTRUCTIVE. This deletes all data in study_areas, study_area_bbls, parcels,
permits, property_records, census_context, ingestion_runs, rejected_records,
and schema_migrations. It does not drop the postgis extension itself, since
that's shared instance-level infrastructure, not application schema.

This is the documented reset path required by IMPLEMENTATION_PLAN.md M2's
exit criteria -- it exists so a broken or half-migrated database can be
rebuilt from db/migrations/ with a single command, not so it gets run
casually. It will not run without an explicit confirmation flag.

Usage:
    python scripts/reset_db.py --yes-drop-all-data
"""

import os
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# Reverse of the FK-dependency order migrations apply in.
TABLES_TO_DROP = [
    "rejected_records",
    "ingestion_runs",
    "census_context",
    "property_records",
    "permits",
    "parcels",
    "study_area_bbls",
    "study_areas",
    "schema_migrations",
]


def main() -> int:
    if "--yes-drop-all-data" not in sys.argv:
        print(__doc__)
        print("Refusing to run without --yes-drop-all-data.")
        return 1

    load_dotenv()
    db_url = os.environ.get("SUPABASE_DB_URL_DIRECT")
    if not db_url:
        print("SUPABASE_DB_URL_DIRECT is not set. Copy .env.example to .env and fill it in.")
        return 1

    print(f"About to DROP these tables from {db_url.split('@')[-1]}:")
    for t in TABLES_TO_DROP:
        print(f"  - {t}")
    confirm = input("Type the database host name shown above to confirm: ").strip()
    if confirm != db_url.split("@")[-1].split("/")[0]:
        print("Confirmation did not match. Aborted.")
        return 1

    with psycopg.connect(db_url, connect_timeout=10, autocommit=True) as conn:
        with conn.cursor() as cur:
            for table in TABLES_TO_DROP:
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                print(f"dropped {table}")

    print("\nRe-running migrations...")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "migrate.py")]
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
