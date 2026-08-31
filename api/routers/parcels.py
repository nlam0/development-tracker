"""GET /api/parcels/{bbl}, /permits, /records -- the per-parcel page (PRD §7C).

The permits and records sub-resources 404 when the parcel itself doesn't
exist, rather than silently returning an empty list, so a bad BBL in a URL
reads the same way at every depth. A spatially-matched permit (D7(b),
`permits.bbl IS NULL`) is therefore never reachable through this router --
it has no parcel to be a sub-resource of, which is the parcel-page
limitation already documented in the README.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from api.db import get_conn
from api.models import ParcelOut, PermitOut, PropertyRecordOut

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
    event_date, latitude, longitude, owner_name, retrieved_at
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


@router.get("/api/parcels/{bbl}/permits", response_model=list[PermitOut])
def get_parcel_permits(
    bbl: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: Connection = Depends(get_conn),
) -> list[PermitOut]:
    bbl = _validate_bbl(bbl)
    _require_parcel_exists(conn, bbl)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {PERMIT_COLUMNS} FROM permits
            WHERE bbl = %s ORDER BY event_date DESC LIMIT %s OFFSET %s;
            """,
            (bbl, limit, offset),
        )
        rows = cur.fetchall()
    return [PermitOut(**r) for r in rows]


@router.get("/api/parcels/{bbl}/records", response_model=list[PropertyRecordOut])
def get_parcel_records(
    bbl: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: Connection = Depends(get_conn),
) -> list[PropertyRecordOut]:
    bbl = _validate_bbl(bbl)
    _require_parcel_exists(conn, bbl)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {RECORD_COLUMNS} FROM property_records
            WHERE bbl = %s ORDER BY recorded_date DESC LIMIT %s OFFSET %s;
            """,
            (bbl, limit, offset),
        )
        rows = cur.fetchall()
    return [PropertyRecordOut(**r) for r in rows]
