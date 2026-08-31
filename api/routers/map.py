"""GET /api/map -- geo-filtered permits as GeoJSON for MapLibre markers (PRD §7B).

Shares api/filters.py's ActivityFilters with /api/activity so identical
filter params return a consistent record set across both (M5's exit
criterion). "Marker clustering at low zoom" (PRD §7B) is MapLibre's own
GeoJSON-source clustering, done client-side against this endpoint's
FeatureCollection -- so this returns every matching point up to a hard cap,
not a paginated slice of one: a client-side clusterer needs the whole
matching set to cluster correctly, and the feed's cursor pagination model
doesn't apply to "show me the markers."
"""

from fastapi import APIRouter, Depends, Query
from psycopg import Connection

from api.db import get_conn
from api.filters import ActivityFilters, get_activity_filters
from api.models import MapFeature, MapFeatureCollection, MapFeatureProperties

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
