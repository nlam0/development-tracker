"""Ingestion run bookkeeping and per-table upsert helpers shared by every adapter.

Every adapter's pipeline stage order ends the same way (PRD §8): upsert,
then record the ingestion timestamp. This module owns both, so an adapter's
own code only has to handle what's genuinely source-specific -- fetch,
validate, normalize, filter -- not how a run gets logged or a natural key
gets upserted.
"""

from collections.abc import Iterable

from psycopg.types.json import Jsonb


def start_run(conn, source: str, *, cursor_start: str | None = None) -> int:
    """Insert a 'running' ingestion_runs row and commit it immediately.

    Committed on its own, ahead of any fetch/transform work, so a run that
    crashes mid-fetch still leaves durable evidence it started (Risk R8: a
    cron job that fails silently is worse than no cron job).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingestion_runs (source, cursor_start, status)
            VALUES (%s, %s, 'running')
            RETURNING id;
            """,
            (source, cursor_start),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(
    conn,
    run_id: int,
    *,
    status: str,
    records_received: int = 0,
    records_inserted: int = 0,
    records_updated: int = 0,
    records_rejected: int = 0,
    cursor_end: str | None = None,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ingestion_runs
            SET completed_at = now(), status = %s, cursor_end = %s,
                records_received = %s, records_inserted = %s,
                records_updated = %s, records_rejected = %s,
                error_message = %s
            WHERE id = %s;
            """,
            (
                status,
                cursor_end,
                records_received,
                records_inserted,
                records_updated,
                records_rejected,
                error_message,
                run_id,
            ),
        )


def record_rejected(conn, run_id: int, source: str, rows: Iterable[tuple[str, dict]]) -> None:
    """Log malformed records rather than silently dropping them (PRD §14)."""
    rows = list(rows)
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO rejected_records (run_id, source, reason, raw)
            VALUES (%s, %s, %s, %s);
            """,
            [(run_id, source, reason, Jsonb(raw)) for reason, raw in rows],
        )


PARCEL_COLUMNS = [
    "bbl",
    "borough",
    "block",
    "lot",
    "address",
    "neighborhood",
    "latitude",
    "longitude",
    "zoning",
    "land_use",
    "lot_area",
    "building_area",
    "commercial_area",
    "residential_area",
    "units_residential",
    "units_total",
    "num_buildings",
    "num_floors",
    "year_built",
    "assessed_total",
    "owner_name",
    "census_tract_2020",
    "census_tract_2010",
    "pluto_version",
]


def upsert_parcels(conn, rows: Iterable[dict]) -> tuple[int, int]:
    """Upsert into parcels on the bbl primary key. Returns (inserted, updated).

    Also derives `geom` from latitude/longitude and sets `retrieved_at`
    server-side, so callers only supply the PARCEL_COLUMNS fields.
    """
    rows = list(rows)
    if not rows:
        return 0, 0
    cols = PARCEL_COLUMNS
    placeholders = ", ".join(f"%({c})s" for c in cols)
    update_cols = [c for c in cols if c != "bbl"]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    sql = f"""
        INSERT INTO parcels ({", ".join(cols)}, geom, retrieved_at)
        VALUES ({placeholders},
                CASE WHEN %(longitude)s IS NOT NULL AND %(latitude)s IS NOT NULL
                     THEN ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)
                     ELSE NULL END,
                now())
        ON CONFLICT (bbl) DO UPDATE SET {set_clause}, geom = EXCLUDED.geom, retrieved_at = now()
        RETURNING (xmax = 0) AS inserted;
    """
    inserted = updated = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(sql, row)
            (was_insert,) = cur.fetchone()
            if was_insert:
                inserted += 1
            else:
                updated += 1
    return inserted, updated
