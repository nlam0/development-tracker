"""PLUTO ingestion -> parcels (M3, IMPLEMENTATION_PLAN.md).

PLUTO is a periodic versioned republication, not a stream (§4): every run
is a full reload of the study area's parcels rather than an incremental
sync. Pinned to version 26v2, the only currently published version
(decision D3) -- filtering on it explicitly means a future PLUTO release
can't silently change parcel attributes mid-research; it has to be repinned
here on purpose.

Usage:
    python -m pipeline.run --source pluto
"""

import os
import sys

import psycopg
from dotenv import load_dotenv

from pipeline.load import finish_run, record_rejected, start_run, upsert_parcels
from pipeline.socrata import fetch_all
from pipeline.transforms.bbl import normalize_bbl_pluto, parse_bbl

DATASET_ID = "64uk-42ks"
PINNED_VERSION = "26v2"
SOURCE = "pluto"

FIELDS = [
    "bbl",
    "address",
    "latitude",
    "longitude",
    "zonedist1",
    "landuse",
    "lotarea",
    "bldgarea",
    "comarea",
    "resarea",
    "unitsres",
    "unitstotal",
    "numbldgs",
    "numfloors",
    "yearbuilt",
    "assesstot",
    "ownername",
    "ct2010",
    "bct2020",
    "version",
]


def _load_study_area_bbls(conn) -> dict[str, str]:
    """bbl -> study_area name, for every BBL M1 resolved into the study area."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT b.bbl, sa.name
            FROM study_area_bbls b
            JOIN study_areas sa ON sa.id = b.study_area_id;
        """)
        return dict(cur.fetchall())


def _to_int(value) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _transform(raw: dict, bbl: str, neighborhood: str) -> dict:
    borough, block, lot = parse_bbl(bbl)
    year_built = _to_int(raw.get("yearbuilt"))
    return {
        "bbl": bbl,
        "borough": borough,
        "block": block,
        "lot": lot,
        "address": raw.get("address"),
        "neighborhood": neighborhood,
        "latitude": _to_float(raw.get("latitude")),
        "longitude": _to_float(raw.get("longitude")),
        "zoning": raw.get("zonedist1"),
        "land_use": raw.get("landuse"),
        "lot_area": _to_int(raw.get("lotarea")),
        "building_area": _to_int(raw.get("bldgarea")),
        "commercial_area": _to_int(raw.get("comarea")),
        "residential_area": _to_int(raw.get("resarea")),
        "units_residential": _to_int(raw.get("unitsres")),
        "units_total": _to_int(raw.get("unitstotal")),
        "num_buildings": _to_int(raw.get("numbldgs")),
        "num_floors": _to_float(raw.get("numfloors")),
        # PLUTO uses 0 as an "unknown" sentinel, not a real construction year.
        "year_built": year_built if year_built else None,
        "assessed_total": _to_int(raw.get("assesstot")),
        "owner_name": raw.get("ownername"),
        "census_tract_2020": raw.get("bct2020"),
        "census_tract_2010": raw.get("ct2010"),
        "pluto_version": raw.get("version") or PINNED_VERSION,
    }


def main() -> int:
    load_dotenv()
    db_url = os.environ.get("SUPABASE_DB_URL_DIRECT")
    if not db_url:
        print("SUPABASE_DB_URL_DIRECT is not set. Copy .env.example to .env and fill it in.")
        return 1
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    with psycopg.connect(db_url, connect_timeout=10) as conn:
        run_id = start_run(conn, SOURCE, cursor_start=PINNED_VERSION)
        try:
            study_area_bbls = _load_study_area_bbls(conn)
            print(f"study area has {len(study_area_bbls)} resolved BBLs")

            received = 0
            rejected: list[tuple[str, dict]] = []
            rows_by_bbl: dict[str, dict] = {}

            for raw in fetch_all(
                DATASET_ID,
                select=",".join(FIELDS),
                where=f"borocode='1' AND version='{PINNED_VERSION}'",
                order="bbl",
                app_token=app_token,
            ):
                received += 1
                raw_bbl = raw.get("bbl")
                if not raw_bbl:
                    rejected.append(("missing bbl", raw))
                    continue
                try:
                    bbl = normalize_bbl_pluto(raw_bbl)
                except (ValueError, TypeError):
                    rejected.append(("unparseable bbl", raw))
                    continue

                neighborhood = study_area_bbls.get(bbl)
                if neighborhood is None:
                    continue  # outside the study area -- filtered, not an error

                rows_by_bbl[bbl] = _transform(raw, bbl, neighborhood)

            if received == 0:
                raise RuntimeError(
                    "received zero records from PLUTO for borocode='1' AND "
                    f"version='{PINNED_VERSION}' -- expected ~42k; dataset "
                    "schema, borough filter, or pinned version may have drifted"
                )

            inserted, updated = upsert_parcels(conn, rows_by_bbl.values())
            record_rejected(conn, run_id, SOURCE, rejected)
            finish_run(
                conn,
                run_id,
                status="success",
                cursor_end=PINNED_VERSION,
                records_received=received,
                records_inserted=inserted,
                records_updated=updated,
                records_rejected=len(rejected),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            finish_run(conn, run_id, status="failed", error_message=str(exc)[:2000])
            conn.commit()
            print(f"PLUTO ingestion failed: {exc}", file=sys.stderr)
            return 1

    print(
        f"received {received}, matched study area {len(rows_by_bbl)}, "
        f"inserted {inserted}, updated {updated}, rejected {len(rejected)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
