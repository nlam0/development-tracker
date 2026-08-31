"""Derive the authoritative BBL allowlist for each study area.

Fetches BBL + centroid lat/long from PLUTO for a bounding box covering all
study areas, loads them into a staging table, and assigns each BBL to a
study area via PostGIS point-in-polygon (ST_Contains). The result is
materialized into study_area_bbls -- the single BBL set every later
ingestion adapter's "filter to study area" stage reads from (PRD §8).

This is a one-off geometry-resolution step, not the recurring PLUTO
ingestion adapter (that's pipeline/sources/pluto.py, built in M3) -- it
only pulls the two columns needed to test containment.

Usage:
    python -m pipeline.study_area.resolve
"""

import os
import sys

import psycopg
import requests
from dotenv import load_dotenv

PLUTO_DATASET = "64uk-42ks"
# Bounding box covering all three study areas with margin (verified against
# study_areas geometry bounds; see IMPLEMENTATION_PLAN.md M1).
BBOX = {"lat_min": 40.704, "lat_max": 40.726, "lon_min": -74.003, "lon_max": -73.971}


def fetch_pluto_centroids(app_token: str | None) -> list[tuple[str, float, float]]:
    params = {
        "$select": "bbl,latitude,longitude",
        "$where": (
            f"borocode='1' AND latitude between {BBOX['lat_min']} and {BBOX['lat_max']} "
            f"AND longitude between {BBOX['lon_min']} and {BBOX['lon_max']} "
            "AND latitude IS NOT NULL AND longitude IS NOT NULL"
        ),
        "$limit": 10000,
    }
    headers = {"X-App-Token": app_token} if app_token else {}
    resp = requests.get(
        f"https://data.cityofnewyork.us/resource/{PLUTO_DATASET}.json",
        params=params,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()
    out = []
    for row in rows:
        raw_bbl = row.get("bbl")
        lat, lon = row.get("latitude"), row.get("longitude")
        if not raw_bbl or lat is None or lon is None:
            continue
        # Inline PLUTO-only normalization for this one-off resolution step.
        # M3 introduces pipeline/transforms/bbl.py as the shared normalizer
        # for all four source formats (IMPLEMENTATION_PLAN.md Risk R3) --
        # switch this to import it once that lands.
        bbl = str(int(float(raw_bbl))).zfill(10)
        out.append((bbl, float(lat), float(lon)))
    return out


def main() -> int:
    load_dotenv()
    db_url = os.environ.get("SUPABASE_DB_URL_DIRECT")
    if not db_url:
        print("SUPABASE_DB_URL_DIRECT is not set. Copy .env.example to .env and fill it in.")
        return 1
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    print("Fetching PLUTO centroids in study-area bounding box...")
    centroids = fetch_pluto_centroids(app_token)
    print(f"  received {len(centroids)} candidate parcels")

    with psycopg.connect(db_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TEMP TABLE _pluto_centroid_staging (
                    bbl CHAR(10) PRIMARY KEY,
                    lat DOUBLE PRECISION NOT NULL,
                    lon DOUBLE PRECISION NOT NULL
                ) ON COMMIT DROP;
            """)
            with cur.copy(
                "COPY _pluto_centroid_staging (bbl, lat, lon) FROM STDIN"
            ) as copy:
                for bbl, lat, lon in centroids:
                    copy.write_row((bbl, lat, lon))

            cur.execute("DELETE FROM study_area_bbls;")
            cur.execute("""
                INSERT INTO study_area_bbls (bbl, study_area_id)
                SELECT s.bbl, sa.id
                FROM _pluto_centroid_staging s
                JOIN study_areas sa
                    ON ST_Contains(sa.geom, ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326));
            """)
            cur.execute("""
                SELECT sa.name, count(*)
                FROM study_area_bbls b
                JOIN study_areas sa ON sa.id = b.study_area_id
                GROUP BY sa.name
                ORDER BY sa.name;
            """)
            for name, count in cur.fetchall():
                print(f"  {name}: {count} parcels")
        conn.commit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
