"""GET /api/parcels/{bbl}, /permits, /records -- the per-parcel page (PRD §7C).

The permits and records sub-resources 404 when the parcel itself doesn't
exist, rather than silently returning an empty list, so a bad BBL in a URL
reads the same way at every depth.

Both sub-resources sort on a non-unique column (event_date, recorded_date)
and page with LIMIT/OFFSET, so they carry `id` as a tiebreaker. Without it
Postgres is free to order rows sharing a date differently between queries,
and consecutive pages of the busiest parcel -- 555 permits, many filed the
same day -- overlapped each other while skipping records entirely. This is
the same hazard /api/activity avoids by paginating on a keyset; offset
pagination is acceptable here only because the total is small and bounded
per parcel, but it still needs a total order to page over. A spatially-matched permit (D7(b),
`permits.bbl IS NULL`) is therefore never reachable through this router --
it has no parcel to be a sub-resource of, which is the parcel-page
limitation already documented in the README.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from api.db import get_conn
from api.models import (
    ParcelOut,
    ParcelPermitsResponse,
    ParcelRecordsResponse,
    PermitOut,
    PropertyRecordOut,
)

router = APIRouter()

BBL_LENGTH = 10

PARCEL_COLUMNS = """
    bbl, borough, block, lot, address, neighborhood, latitude, longitude,
    zoning, land_use, lot_area, building_area, commercial_area, residential_area,
    units_residential, units_total, num_buildings, num_floors, year_built,
    assessed_total, owner_name, census_tract_2020, census_tract_2010,
    pluto_version, retrieved_at
"""

PERMIT_COLUMNS = """
    id, source, external_id, bbl, neighborhood, study_area_match, bin, address,
    filing_number, permit_type, work_type, category, filing_reason, status,
    description, estimated_cost, approved_date, issued_date, expired_date,
    event_date, latitude, longitude, owner_name, retrieved_at, is_current
"""

RECORD_COLUMNS = """
    id, source, external_id, document_id, bbl, bbl_confidence, document_type,
    document_label, property_type, recorded_date, document_date, amount,
    parties, retrieved_at
"""


def _validate_bbl(bbl: str) -> str:
    if len(bbl) != BBL_LENGTH or not bbl.isdigit():
        raise HTTPException(422, f"bbl must be a 10-digit string, got {bbl!r}")
    return bbl


def _page_total(conn: Connection, rows: list, table: str, bbl: str) -> int:
    """Total rows for this parcel, given a page that may or may not carry it.

    `count(*) OVER ()` rides along on the page's own scan, which is both
    cheaper and more consistent than a second query -- but a page that
    returns nothing carries nothing, and an offset past the end would then
    report a total of 0 for a parcel with 555 permits. Falling back to an
    explicit COUNT keeps an empty page honest.
    """
    if rows:
        return rows[0]["total"]
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS total FROM {table} WHERE bbl = %s;", (bbl,))
        return cur.fetchone()["total"]


def _require_parcel_exists(conn: Connection, bbl: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM parcels WHERE bbl = %s;", (bbl,))
        if cur.fetchone() is None:
            raise HTTPException(404, f"no parcel found for bbl {bbl}")


@router.get("/api/parcels/{bbl}", response_model=ParcelOut)
def get_parcel(bbl: str, conn: Connection = Depends(get_conn)) -> ParcelOut:
    bbl = _validate_bbl(bbl)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {PARCEL_COLUMNS} FROM parcels WHERE bbl = %s;", (bbl,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(404, f"no parcel found for bbl {bbl}")
    return ParcelOut(**row)


@router.get("/api/parcels/{bbl}/permits", response_model=ParcelPermitsResponse)
def get_parcel_permits(
    bbl: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: Connection = Depends(get_conn),
) -> ParcelPermitsResponse:
    bbl = _validate_bbl(bbl)
    _require_parcel_exists(conn, bbl)
    with conn.cursor() as cur:
        # count(*) OVER () rides along on the same scan, so `total` can't
        # disagree with the page it describes the way a separate COUNT
        # issued a moment later could.
        cur.execute(
            f"""
            SELECT {PERMIT_COLUMNS}, count(*) OVER () AS total FROM permits
            WHERE bbl = %s ORDER BY event_date DESC, id DESC LIMIT %s OFFSET %s;
            """,
            (bbl, limit, offset),
        )
        rows = cur.fetchall()
    return ParcelPermitsResponse(
        items=[PermitOut(**r) for r in rows],
        total=_page_total(conn, rows, "permits", bbl),
    )


@router.get("/api/parcels/{bbl}/records", response_model=ParcelRecordsResponse)
def get_parcel_records(
    bbl: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: Connection = Depends(get_conn),
) -> ParcelRecordsResponse:
    bbl = _validate_bbl(bbl)
    _require_parcel_exists(conn, bbl)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {RECORD_COLUMNS}, count(*) OVER () AS total FROM property_records
            WHERE bbl = %s ORDER BY recorded_date DESC, id DESC LIMIT %s OFFSET %s;
            """,
            (bbl, limit, offset),
        )
        rows = cur.fetchall()
    return ParcelRecordsResponse(
        items=[PropertyRecordOut(**r) for r in rows],
        total=_page_total(conn, rows, "property_records", bbl),
    )
