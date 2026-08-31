"""Derive the authoritative BBL allowlist for each study area.

Fetches BBL + centroid lat/long from PLUTO for a bounding box covering all
study areas, loads them into a staging table, and assigns each BBL to a
study area via PostGIS point-in-polygon (ST_Contains). The result is
materialized into study_area_bbls -- the single BBL set every later
ingestion adapter's "filter to study area" stage reads from (PRD §8).

This is a one-off geometry-resolution step, not the recurring PLUTO
ingestion adapter (that's pipeline/sources/pluto.py, M3) -- it only pulls
the two columns needed to test containment, via pipeline/transforms/bbl.py
for normalization like every other adapter.

Usage:
    python -m pipeline.study_area.resolve
"""

import os
import sys

import psycopg
from dotenv import load_dotenv

from pipeline.socrata import fetch_all
from pipeline.transforms.bbl import normalize_bbl_pluto

PLUTO_DATASET = "64uk-42ks"
# Bounding box covering all three study areas with margin (verified against
# study_areas geometry bounds; see IMPLEMENTATION_PLAN.md M1).
BBOX = {"lat_min": 40.704, "lat_max": 40.726, "lon_min": -74.003, "lon_max": -73.971}


def fetch_pluto_centroids(app_token: str | None) -> list[tuple[str, float, float]]:
    """Fetch every PLUTO centroid in the study-area bounding box.

    Paged through pipeline/socrata.py rather than issuing a single capped
    request: an earlier version used a bare $limit=10000, which would have
    silently truncated the study area -- and so silently shrunk it -- the
    moment the box held more lots than the cap.
    """
    out = []
    for row in fetch_all(
        PLUTO_DATASET,
        select="bbl,latitude,longitude",
        where=(
            f"borocode='1' AND latitude between {BBOX['lat_min']} and {BBOX['lat_max']} "
            f"AND longitude between {BBOX['lon_min']} and {BBOX['lon_max']} "
            "AND latitude IS NOT NULL AND longitude IS NOT NULL"
        ),
        order="bbl",
        app_token=app_token,
    ):
        raw_bbl = row.get("bbl")
        lat, lon = row.get("latitude"), row.get("longitude")
        if not raw_bbl or lat is None or lon is None:
            continue
        out.append((normalize_bbl_pluto(raw_bbl), float(lat), float(lon)))
    return out


def fetch_pluto_bbls_without_centroids(app_token: str | None) -> list[str]:
    """Fetch every Manhattan PLUTO lot that has no centroid at all.

    These cannot be bounding-box filtered -- having no coordinates is exactly
    what makes them invisible to a spatial query -- so the whole borough's set
    is pulled and narrowed by block membership in SQL (decision D6(b)). It is
    a small set: 398 lots borough-wide, skewed toward air-rights (9xxx) and
    condo lots.
    """
    return [
        normalize_bbl_pluto(row["bbl"])
        for row in fetch_all(
            PLUTO_DATASET,
            select="bbl",
            where="borocode='1' AND latitude IS NULL",
            order="bbl",
            app_token=app_token,
        )
        if row.get("bbl")
    ]


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

    print("Fetching Manhattan PLUTO lots with no centroid (D6(b) fallback)...")
    no_centroid = fetch_pluto_bbls_without_centroids(app_token)
    print(f"  received {len(no_centroid)} lots with no coordinates")

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

            cur.execute("""
                CREATE TEMP TABLE _pluto_no_centroid_staging (
                    bbl CHAR(10) PRIMARY KEY
                ) ON COMMIT DROP;
            """)
            with cur.copy("COPY _pluto_no_centroid_staging (bbl) FROM STDIN") as copy:
                for bbl in no_centroid:
                    copy.write_row((bbl,))

            cur.execute("DELETE FROM study_area_bbls;")
            cur.execute("""
                INSERT INTO study_area_bbls (bbl, study_area_id, resolution_method)
                SELECT s.bbl, sa.id, 'centroid'
                FROM _pluto_centroid_staging s
                JOIN study_areas sa
                    ON ST_Contains(sa.geom, ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326));
            """)

            # D6(b): a centroid-less lot joins the study area when its block
            # unambiguously belongs to one. A block straddling two study areas
            # (the Division St split) is left unresolved rather than assigned
            # by majority vote -- that would be a silent research judgment.
            cur.execute("""
                WITH block_area AS (
                    SELECT substring(bbl, 1, 6) AS blk,
                           min(study_area_id)   AS study_area_id,
                           count(DISTINCT study_area_id) AS n_areas
                    FROM study_area_bbls
                    WHERE resolution_method = 'centroid'
                    GROUP BY 1
                )
                INSERT INTO study_area_bbls (bbl, study_area_id, resolution_method)
                SELECT n.bbl, ba.study_area_id, 'block_membership'
                FROM _pluto_no_centroid_staging n
                JOIN block_area ba ON ba.blk = substring(n.bbl, 1, 6)
                WHERE ba.n_areas = 1
                  AND NOT EXISTS (SELECT 1 FROM study_area_bbls x WHERE x.bbl = n.bbl);
            """)
            print(f"  admitted {cur.rowcount} lots by block membership")

            cur.execute("""
                WITH block_area AS (
                    SELECT substring(bbl, 1, 6) AS blk,
                           count(DISTINCT study_area_id) AS n_areas
                    FROM study_area_bbls
                    WHERE resolution_method = 'centroid'
                    GROUP BY 1
                )
                SELECT n.bbl FROM _pluto_no_centroid_staging n
                JOIN block_area ba ON ba.blk = substring(n.bbl, 1, 6)
                WHERE ba.n_areas > 1;
            """)
            ambiguous = [r[0] for r in cur.fetchall()]
            if ambiguous:
                print(
                    f"  {len(ambiguous)} centroid-less lots left unresolved "
                    f"(block spans >1 study area): {', '.join(ambiguous)}"
                )

            cur.execute("""
                SELECT sa.name, b.resolution_method, count(*)
                FROM study_area_bbls b
                JOIN study_areas sa ON sa.id = b.study_area_id
                GROUP BY sa.name, b.resolution_method
                ORDER BY sa.name, b.resolution_method;
            """)
            for name, method, count in cur.fetchall():
                print(f"  {name} [{method}]: {count} parcels")
        conn.commit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
