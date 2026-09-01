"""DOB NOW ingestion -> permits (M4, IMPLEMENTATION_PLAN.md).

DOB NOW's *work permits* dataset (rbx6-tga4, "DOB NOW: Build - Approved
Permits") carries `work_type`, but `work_type` is a construction *discipline*
(Plumbing, Sidewalk Shed, Sprinklers, ...), not the new-building / alteration
/ demolition classification `permits.category` needs for the map (PRD §7B).
That classification lives on the *job filing* the permit is issued under, in
a separate dataset (w9ak-ipjd, "DOB NOW: Build - Job Application Filings")
as `job_type`, joined back by `job_filing_number`. This was discovered by
querying both datasets directly during M4, not assumed from the plan text --
§3's design note describing a `work_type` -> category mapping predates this
and is superseded by CATEGORY_MAP below.

Study-area membership follows decision D7(b): a permit whose own `bbl` is in
the M1-resolved allowlist enters with `study_area_match='bbl'` and keeps that
bbl; otherwise, if its own lat/long falls inside a study-area polygon, it
enters with `study_area_match='spatial'` and a null bbl (its bbl -- if any --
has no `parcels` row, so the FK can't hold it). This is why fetching can't be
a single BBL-filtered query: it has to also cover the bounding box, the same
one `pipeline/study_area/resolve.py` uses, to see permits an allowlist-only
query would silently miss (Risk R12).

Unlike PLUTO, this is a full reload of the study area's current DOB NOW
state every run, not a true incremental sync on `approved_date` as
IMPLEMENTATION_PLAN.md's M4 line originally sketched. Three reasons, found
while building this adapter: (1) a permit's status changes after it first
appears (Issued -> Signed-off) and a pure append would never refresh it;
(2) newly-appearing spatial-only matches (Risk R12) require re-scanning the
bounding box regardless of cursor position; (3) study-area volume is small
enough (~23k records total) that a full reload costs a handful of chunked
requests, not a meaningful daily burden. Idempotent upsert makes this safe,
proven the same way M3 proved it: a second run reports zero inserted.

Usage:
    python -m pipeline.run --source dob_now
"""

import hashlib
import os
import sys
from collections.abc import Iterable

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from pipeline.load import (
    finish_run,
    mark_absent_after_full_reload,
    purge_rejected_for_source,
    record_rejected,
    start_run,
    upsert_permits,
)
from pipeline.socrata import fetch_all
from pipeline.study_area.resolve import BBOX
from pipeline.transforms.bbl import normalize_bbl_dob_now
from pipeline.transforms.dates import parse_iso_date
from pipeline.transforms.money import parse_cost

PERMITS_DATASET = "rbx6-tga4"
JOB_FILINGS_DATASET = "w9ak-ipjd"
SOURCE = "dob_now"

# job_filing_number/work_permit carry this literal truncated text, not a real
# identifier, on approved-but-unissued-permit filings (Risk R1).
SENTINEL_FILING = "Permit is no"
SENTINEL_PERMIT = "Permit is not yet issued"

BBL_CHUNK_SIZE = 300
FILING_CHUNK_SIZE = 300

PERMIT_FIELDS = [
    "job_filing_number",
    "work_permit",
    "sequence_number",
    "filing_reason",
    "house_no",
    "street_name",
    "work_type",
    "permit_status",
    "job_description",
    "estimated_job_costs",
    "owner_name",
    "approved_date",
    "issued_date",
    "expired_date",
    "bin",
    "bbl",
    "latitude",
    "longitude",
    "tracking_number",
]

# job_type (DOB NOW: Build - Job Application Filings) -> permits.category.
# Confirmed against the live dataset (M4): these are the only six values in
# use. An unrecognized or unresolvable value falls back to 'other' rather
# than failing the run -- Risk R10, upstream schema drift shouldn't be fatal
# for a classification field the way it is for an identifier.
CATEGORY_MAP = {
    "New Building": "new_building",
    "ALT-CO - New Building with Existing Elements to Remain": "new_building",
    "Full Demolition": "demolition",
    "Alteration": "alteration",
    "Alteration CO": "alteration",
    "No Work": "other",
}


def _chunks(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _is_sentinel(filing: str | None, permit: str | None) -> bool:
    return filing in (None, "", SENTINEL_FILING) or permit in (None, "", SENTINEL_PERMIT)


def external_id(raw: dict) -> str:
    """Composite natural key per Risk R1's corrected mitigation, with a hash
    fallback for the sentinel/null case the composite key can't represent.

    Measured against the study area (post-M3 audit): filing + work_permit +
    sequence_number alone collapses 1,771 distinct permits; adding work_type
    + tracking_number brings that to zero. tracking_number was non-null on
    every one of the 22,960 study-area records checked.
    """
    filing = raw.get("job_filing_number")
    permit = raw.get("work_permit")
    sequence = raw.get("sequence_number")
    work_type = raw.get("work_type")
    tracking = raw.get("tracking_number")

    if _is_sentinel(filing, permit) or not sequence or not work_type or not tracking:
        basis = "|".join(
            str(raw.get(k)) for k in ("bbl", "work_type", "approved_date", "job_description")
        )
        digest = hashlib.sha256(basis.encode()).hexdigest()[:32]
        return f"hash:{digest}"
    return f"{filing}|{permit}|{sequence}|{work_type}|{tracking}"


def fetch_permits(app_token: str | None, study_area_bbls: dict[str, str]) -> dict[str, dict]:
    """Fetch every DOB NOW permit that could plausibly be in the study area.

    Two queries, merged and deduped by external_id: BBL-allowlist chunks
    (catches everything PLUTO resolved, coordinates or not) and the same
    bounding box resolve.py uses (catches spatially-matchable permits an
    allowlist-only query would miss -- Risk R12/D7(b)).
    """
    bbls = [int(b) for b in study_area_bbls]
    records: dict[str, dict] = {}

    for chunk in _chunks(bbls, BBL_CHUNK_SIZE):
        where = f"bbl in ({','.join(str(b) for b in chunk)})"
        for raw in fetch_all(
            PERMITS_DATASET,
            select=",".join(PERMIT_FIELDS),
            where=where,
            order="tracking_number",
            app_token=app_token,
        ):
            records[external_id(raw)] = raw

    bbox_where = (
        f"latitude between {BBOX['lat_min']} and {BBOX['lat_max']} "
        f"AND longitude between {BBOX['lon_min']} and {BBOX['lon_max']}"
    )
    for raw in fetch_all(
        PERMITS_DATASET,
        select=",".join(PERMIT_FIELDS),
        where=bbox_where,
        order="tracking_number",
        app_token=app_token,
    ):
        records[external_id(raw)] = raw

    return records


def fetch_job_types(app_token: str | None, job_filing_numbers: set[str]) -> dict[str, str]:
    """job_filing_number -> job_type, chunked over the Job Application Filings dataset."""
    out: dict[str, str] = {}
    numbers = sorted(job_filing_numbers)
    for chunk in _chunks(numbers, FILING_CHUNK_SIZE):
        quoted = ",".join("'" + n.replace("'", "''") + "'" for n in chunk)
        where = f"job_filing_number in ({quoted})"
        for raw in fetch_all(
            JOB_FILINGS_DATASET,
            select="job_filing_number,job_type",
            where=where,
            order="job_filing_number",
            app_token=app_token,
        ):
            if raw.get("job_type"):
                out[raw["job_filing_number"]] = raw["job_type"]
    return out


def resolve_spatial_matches(
    conn, candidates: list[tuple[str, float, float]]
) -> dict[str, str]:
    """external_id -> neighborhood, for candidates whose point falls inside a
    study-area polygon. Point-in-polygon stays in Postgres/PostGIS -- the
    same ST_Contains test resolve.py uses -- rather than pulling a geometry
    library into the pipeline for one adapter's fallback path.
    """
    if not candidates:
        return {}
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE _dob_now_spatial_candidates (
                external_id TEXT PRIMARY KEY,
                lat DOUBLE PRECISION NOT NULL,
                lon DOUBLE PRECISION NOT NULL
            ) ON COMMIT DROP;
        """)
        with cur.copy(
            "COPY _dob_now_spatial_candidates (external_id, lat, lon) FROM STDIN"
        ) as copy:
            for eid, lat, lon in candidates:
                copy.write_row((eid, lat, lon))

        cur.execute("""
            SELECT c.external_id, sa.name
            FROM _dob_now_spatial_candidates c
            JOIN study_areas sa
                ON ST_Contains(sa.geom, ST_SetSRID(ST_MakePoint(c.lon, c.lat), 4326));
        """)
        return dict(cur.fetchall())


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _transform(raw: dict, eid: str, bbl: str | None, neighborhood: str, match: str,
               category: str) -> dict:
    approved = parse_iso_date(raw.get("approved_date"))
    issued = parse_iso_date(raw.get("issued_date"))
    event_date = issued or approved
    if event_date is None:
        raise ValueError("missing event date (both approved_date and issued_date are null)")

    house_no = raw.get("house_no") or ""
    street_name = raw.get("street_name") or ""
    address = f"{house_no} {street_name}".strip() or None

    return {
        "source": SOURCE,
        "external_id": eid,
        "bbl": bbl,
        "bin": raw.get("bin"),
        "address": address,
        "filing_number": raw.get("job_filing_number"),
        "permit_type": None,  # not present in this dataset; see module docstring
        "work_type": raw.get("work_type"),
        "category": category,
        "filing_reason": raw.get("filing_reason"),
        "status": raw.get("permit_status"),
        "description": raw.get("job_description"),
        "estimated_cost": parse_cost(raw.get("estimated_job_costs")),
        "approved_date": approved,
        "issued_date": issued,
        "expired_date": parse_iso_date(raw.get("expired_date")),
        "event_date": event_date,
        "latitude": _to_float(raw.get("latitude")),
        "longitude": _to_float(raw.get("longitude")),
        "owner_name": raw.get("owner_name"),
        "neighborhood": neighborhood,
        "study_area_match": match,
        "raw": Jsonb(raw),
    }


def process_records(
    records: dict[str, dict],
    membership: dict[str, tuple[str | None, str, str]],
    job_types: dict[str, str],
) -> tuple[dict[str, dict], list[tuple[str, dict]], int]:
    """Validate, normalize, and categorize records already resolved into the
    study area. Pure -- no network or DB -- so it's unit-testable.

    `membership` is external_id -> (bbl_or_None, neighborhood, match_type)
    for records already known to be in the study area; anything not present
    in `membership` is filtered out before this is called, exactly as
    PLUTO's process_records filters out-of-area rows rather than rejecting
    them (not being in the study area isn't a data error).
    """
    received = len(records)
    rejected: list[tuple[str, dict]] = []
    rows_by_id: dict[str, dict] = {}

    for eid, raw in records.items():
        if eid not in membership:
            continue
        bbl, neighborhood, match = membership[eid]
        filing = raw.get("job_filing_number")
        category = CATEGORY_MAP.get(job_types.get(filing), "other")
        try:
            rows_by_id[eid] = _transform(raw, eid, bbl, neighborhood, match, category)
        except (ValueError, TypeError, ArithmeticError) as exc:
            rejected.append((f"unparseable field: {exc}", raw))

    return rows_by_id, rejected, received


def _load_study_area_bbls(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT b.bbl, sa.name
            FROM study_area_bbls b
            JOIN study_areas sa ON sa.id = b.study_area_id;
        """)
        return dict(cur.fetchall())


def _resolve_membership(
    conn, records: dict[str, dict], study_area_bbls: dict[str, str]
) -> dict[str, tuple[str | None, str, str]]:
    membership: dict[str, tuple[str | None, str, str]] = {}
    spatial_candidates: list[tuple[str, float, float]] = []

    for eid, raw in records.items():
        raw_bbl = raw.get("bbl")
        normalized_bbl = None
        if raw_bbl is not None:
            try:
                normalized_bbl = normalize_bbl_dob_now(raw_bbl)
            except (ValueError, TypeError):
                normalized_bbl = None

        if normalized_bbl is not None and normalized_bbl in study_area_bbls:
            membership[eid] = (normalized_bbl, study_area_bbls[normalized_bbl], "bbl")
            continue

        lat, lon = raw.get("latitude"), raw.get("longitude")
        if lat not in (None, "") and lon not in (None, ""):
            spatial_candidates.append((eid, float(lat), float(lon)))
        # else: no allowlisted bbl and no coordinates -- can't place this
        # record in the study area at all; it's simply excluded, same as an
        # out-of-area PLUTO row.

    spatial_matches = resolve_spatial_matches(conn, spatial_candidates)
    for eid, neighborhood in spatial_matches.items():
        membership[eid] = (None, neighborhood, "spatial")

    return membership


def main() -> int:
    load_dotenv()
    db_url = os.environ.get("SUPABASE_DB_URL_DIRECT")
    if not db_url:
        print("SUPABASE_DB_URL_DIRECT is not set. Copy .env.example to .env and fill it in.")
        return 1
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    with psycopg.connect(db_url, connect_timeout=10) as conn:
        run_id, run_started_at = start_run(conn, SOURCE)
        try:
            study_area_bbls = _load_study_area_bbls(conn)
            print(f"study area has {len(study_area_bbls)} resolved BBLs")

            records = fetch_permits(app_token, study_area_bbls)
            received = len(records)
            print(f"fetched {received} candidate permits (bbl allowlist + bounding box)")

            if received == 0:
                raise RuntimeError(
                    "received zero DOB NOW records for the study-area bbl allowlist and "
                    "bounding box -- expected on the order of 20k; dataset schema, bbox, "
                    "or allowlist may have drifted"
                )

            membership = _resolve_membership(conn, records, study_area_bbls)
            print(f"{len(membership)} of {received} fall inside the study area")

            filing_numbers = {
                raw["job_filing_number"]
                for eid, raw in records.items()
                if eid in membership
                and not _is_sentinel(raw.get("job_filing_number"), raw.get("work_permit"))
            }
            job_types = fetch_job_types(app_token, filing_numbers)
            print(f"resolved job_type for {len(job_types)} of {len(filing_numbers)} filings")

            rows_by_id, rejected, _ = process_records(records, membership, job_types)

            inserted, updated = upsert_permits(conn, rows_by_id.values())
            # Full reload every run (see module docstring), so this run's
            # rejects supersede the last one's.
            purge_rejected_for_source(conn, SOURCE)
            record_rejected(conn, run_id, SOURCE, rejected)
            # Scoped to source='dob_now': this run re-fetched DOB NOW's whole
            # study-area set and nothing else, so it can only speak to its own
            # rows. Once DOB legacy shares this table, an unscoped sweep here
            # would mark every legacy permit absent on the first DOB NOW run.
            # Safe against a wholesale wipe only because the zero-record guard
            # above already rejected an empty fetch.
            marked_absent = mark_absent_after_full_reload(
                conn, "permits", run_started_at, source=SOURCE
            )
            finish_run(
                conn,
                run_id,
                status="success",
                records_received=received,
                records_inserted=inserted,
                records_updated=updated,
                records_rejected=len(rejected),
                records_marked_absent=marked_absent,
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            finish_run(conn, run_id, status="failed", error_message=str(exc)[:2000])
            conn.commit()
            print(f"DOB NOW ingestion failed: {exc}", file=sys.stderr)
            return 1

    print(
        f"received {received}, in study area {len(membership)}, "
        f"inserted {inserted}, updated {updated}, rejected {len(rejected)}, "
        f"marked absent {marked_absent}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
