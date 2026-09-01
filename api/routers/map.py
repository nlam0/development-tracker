"""GET /api/map -- geo-filtered permits as GeoJSON for MapLibre markers (PRD §7B).

Shares api/filters.py's ActivityFilters with /api/activity so identical
filter params return a consistent record set across both (M5's exit
criterion). "Marker clustering at low zoom" (PRD §7B) is MapLibre's own
GeoJSON-source clustering, done client-side against this endpoint's
FeatureCollection -- so this returns every matching point up to a hard cap,
not a paginated slice of one: a client-side clusterer needs the whole
matching set to cluster correctly, and the feed's cursor pagination model
doesn't apply to "show me the markers."

That hard cap was silently lossy. Every one of the study area's 10,364
permits carries coordinates, so an unfiltered request returned the 5,000
newest and dropped 5,364 -- 52% of the dataset -- while presenting itself
as the complete matching set this docstring promised. Two changes fix it:

  1. `bbox` restricts the query to the map's current viewport, using the
     GIST index on permits.geom, so a zoomed-in map asks for what it can
     actually show instead of the whole study area. This is the real
     answer to the cap: at any zoom where individual markers matter, the
     viewport holds far fewer than 5,000 points.
  2. `total` and `truncated` are returned regardless, so a response that
     *is* capped says so. Silent truncation is the part that made this a
     research-correctness bug rather than a performance limit.

`bbox` is map-only and deliberately not part of ActivityFilters: the feed
is chronological, not spatial, and the shared filter set is what
guarantees feed and map agree. It lives here for the same reason sort and
cursor live in activity.py.

GET /api/study-areas is a small addition beyond PRD §11's literal six --
found missing while building M6's map view. PRD §7B requires the
study-area boundary to be visible on the map, and CLAUDE.md is explicit
that boundaries "must be stored explicitly in the application (not
hardcoded per-query)" -- so the frontend needs a real source for that
geometry rather than a copy-pasted polygon baked into web/. This is a
read-only view over study_areas.geom, the same table M1 already treats as
the single source of truth for the boundary everywhere else.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from api.db import get_conn
from api.filters import ActivityFilters, get_activity_filters
from api.models import (
    MapFeature,
    MapFeatureCollection,
    MapFeatureProperties,
    StudyAreaFeature,
    StudyAreaFeatureCollection,
    StudyAreaProperties,
)

router = APIRouter()

MAP_HARD_LIMIT = 5000

# Coordinate sanity bounds. Not study-area bounds -- a viewport legitimately
# extends past the study area whenever the map is zoomed out -- just the
# limits of a well-formed WGS84 pair, so a malformed bbox fails as a 422
# rather than as an empty map the caller has to diagnose.
MIN_LON, MAX_LON = -180.0, 180.0
MIN_LAT, MAX_LAT = -90.0, 90.0

BBOX_PARTS = 4


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    """Parse `west,south,east,north` into floats, or None when unset.

    Ordering follows the OGC/GeoJSON convention (min lon, min lat, max lon,
    max lat), which is also the order MapLibre's `map.getBounds().toArray()`
    flattens to, so the frontend passes it through without rearranging.
    """
    if bbox is None:
        return None
    parts = [p.strip() for p in bbox.split(",")]
    if len(parts) != BBOX_PARTS:
        raise HTTPException(422, f"bbox must be 'west,south,east,north', got {bbox!r}")
    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(422, f"bbox values must be numbers, got {bbox!r}") from None
    if not (MIN_LON <= west <= MAX_LON and MIN_LON <= east <= MAX_LON):
        raise HTTPException(422, f"bbox longitudes must be within [-180, 180], got {bbox!r}")
    if not (MIN_LAT <= south <= MAX_LAT and MIN_LAT <= north <= MAX_LAT):
        raise HTTPException(422, f"bbox latitudes must be within [-90, 90], got {bbox!r}")
    if west >= east or south >= north:
        raise HTTPException(422, f"bbox must have west < east and south < north, got {bbox!r}")
    return west, south, east, north


@router.get("/api/map", response_model=MapFeatureCollection)
def get_map(
    filters: ActivityFilters = Depends(get_activity_filters),
    bbox: str | None = Query(
        None,
        description="viewport as 'west,south,east,north' in WGS84; omit for the whole study area",
    ),
    limit: int = Query(MAP_HARD_LIMIT, ge=1, le=MAP_HARD_LIMIT),
    conn: Connection = Depends(get_conn),
) -> MapFeatureCollection:
    where_sql, params = filters.where_clause()
    where_sql += " AND latitude IS NOT NULL AND longitude IS NOT NULL"

    bounds = parse_bbox(bbox)
    if bounds is not None:
        # ST_Intersects, not the bare `&&` overlap operator. `&&` compares
        # PostGIS's cached bounding boxes, which are stored in float4 -- so
        # near an edge it rounds outward and returns points fractionally
        # outside the viewport (caught by test_map_bbox_restricts_to_the_
        # viewport: a point at 40.712996 matched a box starting at 40.713).
        # ST_Intersects still uses the GIST index via an internal `&&`, then
        # rechecks exactly, which is what a viewport query has to mean.
        where_sql += " AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
        params = params + list(bounds)

    # count(*) OVER () is evaluated across the whole filtered set before
    # LIMIT applies, so `total` is the true match count in the same scan --
    # no second COUNT query, and no window where the two could disagree.
    sql = f"""
        SELECT id, bbl, neighborhood, category, address, event_date, estimated_cost,
               latitude, longitude, count(*) OVER () AS total
        FROM permits
        WHERE {where_sql}
        ORDER BY event_date DESC
        LIMIT %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [limit])
        rows = cur.fetchall()

    total = rows[0]["total"] if rows else 0
    features = [
        MapFeature(
            geometry={"type": "Point", "coordinates": (r["longitude"], r["latitude"])},
            properties=MapFeatureProperties(**r),
        )
        for r in rows
    ]
    return MapFeatureCollection(features=features, total=total, truncated=len(features) < total)


@router.get("/api/study-areas", response_model=StudyAreaFeatureCollection)
def get_study_areas(conn: Connection = Depends(get_conn)) -> StudyAreaFeatureCollection:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, definition_note, ST_AsGeoJSON(geom)::json AS geometry FROM study_areas;"
        )
        rows = cur.fetchall()
    features = [
        StudyAreaFeature(
            geometry=r["geometry"],
            properties=StudyAreaProperties(name=r["name"], definition_note=r["definition_note"]),
        )
        for r in rows
    ]
    return StudyAreaFeatureCollection(features=features)
