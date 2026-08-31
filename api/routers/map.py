"""GET /api/map -- geo-filtered permits as GeoJSON for MapLibre markers (PRD §7B).

Shares api/filters.py's ActivityFilters with /api/activity so identical
filter params return a consistent record set across both (M5's exit
criterion). "Marker clustering at low zoom" (PRD §7B) is MapLibre's own
GeoJSON-source clustering, done client-side against this endpoint's
FeatureCollection -- so this returns every matching point up to a hard cap,
not a paginated slice of one: a client-side clusterer needs the whole
matching set to cluster correctly, and the feed's cursor pagination model
doesn't apply to "show me the markers."

GET /api/study-areas is a small addition beyond PRD §11's literal six --
found missing while building M6's map view. PRD §7B requires the
study-area boundary to be visible on the map, and CLAUDE.md is explicit
that boundaries "must be stored explicitly in the application (not
hardcoded per-query)" -- so the frontend needs a real source for that
geometry rather than a copy-pasted polygon baked into web/. This is a
read-only view over study_areas.geom, the same table M1 already treats as
the single source of truth for the boundary everywhere else.
"""

from fastapi import APIRouter, Depends, Query
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


@router.get("/api/map", response_model=MapFeatureCollection)
def get_map(
    filters: ActivityFilters = Depends(get_activity_filters),
    limit: int = Query(MAP_HARD_LIMIT, ge=1, le=MAP_HARD_LIMIT),
    conn: Connection = Depends(get_conn),
) -> MapFeatureCollection:
    where_sql, params = filters.where_clause()
    sql = f"""
        SELECT id, bbl, neighborhood, category, address, event_date, estimated_cost,
               latitude, longitude
        FROM permits
        WHERE {where_sql} AND latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY event_date DESC
        LIMIT %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + [limit])
        rows = cur.fetchall()

    features = [
        MapFeature(
            geometry={"type": "Point", "coordinates": (r["longitude"], r["latitude"])},
            properties=MapFeatureProperties(**r),
        )
        for r in rows
    ]
    return MapFeatureCollection(features=features)


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
