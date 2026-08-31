"""Load pipeline/study_area/boundaries.geojson into the study_areas table.

boundaries.geojson is a checked-in, hand-produced artifact (see IMPLEMENTATION_PLAN.md
decision D1): the NYC DCP 2020 NTA polygons for 'Chinatown-Two Bridges' and 'Lower
East Side', with the former split into Chinatown and Two Bridges along the Division
Street centerline. Regenerating it is a deliberate one-time GIS step, not something
this loader does -- this script only upserts the already-built geometry into Postgres.

Usage:
    python -m pipeline.study_area.load_boundaries
"""

import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

BOUNDARIES_PATH = Path(__file__).resolve().parent / "boundaries.geojson"


def main() -> int:
    load_dotenv()
    db_url = os.environ.get("SUPABASE_DB_URL_DIRECT")
    if not db_url:
        print("SUPABASE_DB_URL_DIRECT is not set. Copy .env.example to .env and fill it in.")
        return 1

    data = json.loads(BOUNDARIES_PATH.read_text())
    features = data["features"]

    with psycopg.connect(db_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            for feat in features:
                name = feat["properties"]["name"]
                note = feat["properties"]["definition_note"]
                geom_json = json.dumps(feat["geometry"])
                cur.execute(
                    """
                    INSERT INTO study_areas (name, geom, definition_note)
                    VALUES (%s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)
                    ON CONFLICT (name) DO UPDATE SET
                        geom = EXCLUDED.geom,
                        definition_note = EXCLUDED.definition_note;
                    """,
                    (name, geom_json, note),
                )
                print(f"upserted study area: {name}")
        conn.commit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
