"""Schema checks against the live Supabase database (M2).

Skipped automatically when SUPABASE_DB_URL_DIRECT isn't configured (see
tests/conftest.py) -- these are integration checks on real infrastructure,
not unit tests, and shouldn't fail a CI run that has no DB credentials.

The point isn't to re-verify every column -- migrations already define the
schema declaratively -- it's to lock in the constraints that ingestion
correctness actually depends on: the idempotency-critical UNIQUE
constraints (PRD §14) and the FK relationships the pipeline stage order
assumes (parcels loads before permits/property_records -- M3 before M4/M8).
"""

EXPECTED_TABLES = {
    "study_areas",
    "study_area_bbls",
    "parcels",
    "permits",
    "property_records",
    "census_context",
    "ingestion_runs",
    "rejected_records",
}


# Constraint introspection goes through pg_catalog rather than
# information_schema. The information_schema constraint views only expose
# constraints on tables the caller owns or holds a privilege other than
# SELECT on, so under CI's read-only role they returned nothing at all and
# these tests failed with empty result sets rather than real disagreements.
# pg_constraint is readable by any role, and is the more direct source
# besides -- `conkey` is the column list, no three-way join required.
def _constraint_columns(cur, table: str, contype: str) -> list[set[str]]:
    """Column sets for each constraint of `contype` on `table`.

    contype follows pg_constraint: 'u' unique, 'p' primary key, 'f' foreign key.
    """
    cur.execute(
        """
        SELECT con.conname, att.attname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = k.attnum
        WHERE nsp.nspname = 'public' AND rel.relname = %s AND con.contype = %s
        ORDER BY con.conname, k.ord;
        """,
        (table, contype),
    )
    by_constraint: dict[str, set[str]] = {}
    for name, col in cur.fetchall():
        by_constraint.setdefault(name, set()).add(col)
    return list(by_constraint.values())


def test_all_expected_tables_exist(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"
        )
        tables = {row[0] for row in cur.fetchall()}
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables: {missing}"


def test_permits_and_property_records_have_idempotency_constraint(db_conn):
    with db_conn.cursor() as cur:
        permits_uniques = _constraint_columns(cur, "permits", "u")
        records_uniques = _constraint_columns(cur, "property_records", "u")
    assert {"source", "external_id"} in permits_uniques
    assert {"source", "external_id"} in records_uniques


def test_census_context_composite_primary_key(db_conn):
    with db_conn.cursor() as cur:
        pk = _constraint_columns(cur, "census_context", "p")
    assert pk == [{"geography_id", "tract_vintage", "year", "variable"}]


def test_foreign_keys_reflect_pipeline_load_order(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT rel.relname, att.attname, frel.relname, fatt.attname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            JOIN pg_class frel ON frel.oid = con.confrelid
            JOIN unnest(con.conkey, con.confkey)
                 WITH ORDINALITY AS k(attnum, fattnum, ord) ON TRUE
            JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = k.attnum
            JOIN pg_attribute fatt ON fatt.attrelid = frel.oid AND fatt.attnum = k.fattnum
            WHERE nsp.nspname = 'public' AND con.contype = 'f';
            """
        )
        fks = {(row[0], row[1]): (row[2], row[3]) for row in cur.fetchall()}

    assert fks[("permits", "bbl")] == ("parcels", "bbl")
    assert fks[("property_records", "bbl")] == ("parcels", "bbl")
    assert fks[("parcels", "neighborhood")] == ("study_areas", "name")
    assert fks[("study_area_bbls", "study_area_id")] == ("study_areas", "id")
    assert fks[("rejected_records", "run_id")] == ("ingestion_runs", "id")


def test_migrations_are_idempotent(db_conn):
    """schema_migrations should have exactly one row per file in db/migrations/."""
    from pathlib import Path

    migrations_dir = Path(__file__).resolve().parent.parent / "db" / "migrations"
    expected = {f.name for f in migrations_dir.glob("*.sql")}

    with db_conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations;")
        applied = {row[0] for row in cur.fetchall()}

    assert applied == expected


def test_permits_carry_study_area_match_and_neighborhood(db_conn):
    """Decision D7(b): a spatially-matched permit has no parcels row to join
    through, so permits must carry their own neighborhood and record how they
    entered the study area."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, is_nullable FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'permits'
              AND column_name IN ('neighborhood', 'study_area_match');
        """)
        cols = dict(cur.fetchall())
    assert cols.get("study_area_match") == "NO", "study_area_match must be NOT NULL"
    assert "neighborhood" in cols


def test_study_area_bbls_records_resolution_method(db_conn):
    """Decision D6(b): how a BBL entered the study area is research metadata."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT resolution_method FROM study_area_bbls;")
        methods = {row[0] for row in cur.fetchall()}
    assert methods <= {"centroid", "block_membership"}
    assert "centroid" in methods
