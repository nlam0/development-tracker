"""Derive boundaries.geojson from source city data. Reproduces decision D1.

The NYC DCP 2020 Neighborhood Tabulation Areas dataset has no separate polygon
for Chinatown vs. Two Bridges -- it publishes a single combined NTA,
'Chinatown-Two Bridges' (code MN0301). This project treats them as two
distinct study areas (PRD §5), so this script splits that polygon along the
Division Street centerline -- the conventional dividing line between the two
neighborhoods -- and takes the separate 'Lower East Side' NTA as-is.

This is a research judgment, not official City geography (Risk R6): the
split line and the choice to draw it there are recorded in each feature's
definition_note, which is what /methodology reproduces to the user.

Run this only to regenerate boundaries.geojson (e.g. to revise the split
line). Normal ingestion never re-derives boundaries -- it reads the
committed boundaries.geojson via load_boundaries.py.

Usage:
    python -m pipeline.study_area.build_boundaries
"""

import json
import sys
from pathlib import Path

import requests
from shapely.geometry import LineString, mapping, shape
from shapely.ops import linemerge, split, unary_union

NTA_DATASET = "9nt8-h7nd"  # 2020 Neighborhood Tabulation Areas (NTAs)
CENTERLINE_DATASET = "inkn-q76z"  # NYC DOT LION street Centerline
OUTPUT_PATH = Path(__file__).resolve().parent / "boundaries.geojson"

# Division St's own mapped extent (Chatham Sq to Grand/Pike) is shorter than
# the NTA polygon's east-west span; extend the line's bearing this far past
# the polygon bbox on both ends so it fully bisects the polygon. The polygon
# spans ~0.017 degrees east-west, so this overshoots comfortably.
EXTENSION_DEGREES = 0.02

CHINATOWN_NOTE = (
    "Derived from the NYC DCP 2020 Neighborhood Tabulation Area "
    "'Chinatown-Two Bridges' (NTA2020 code MN0301), split along the "
    "Division Street centerline (NYC DOT LION centerline dataset, "
    "street segments matching full_street_name='DIVISION ST' in "
    "Manhattan). This NTA does not distinguish Chinatown from Two "
    "Bridges; the split point and the decision to treat them as two "
    "study areas are researcher judgments for this project, not "
    "official City geography. Chinatown is the portion north of the "
    "Division Street line."
)
TWO_BRIDGES_NOTE = (
    "Derived from the NYC DCP 2020 Neighborhood Tabulation Area "
    "'Chinatown-Two Bridges' (NTA2020 code MN0301), split along the "
    "Division Street centerline (NYC DOT LION centerline dataset, "
    "street segments matching full_street_name='DIVISION ST' in "
    "Manhattan). This NTA does not distinguish Chinatown from Two "
    "Bridges; the split point and the decision to treat them as two "
    "study areas are researcher judgments for this project, not "
    "official City geography. Two Bridges is the portion south of "
    "the Division Street line, toward the Manhattan and Brooklyn "
    "Bridge approaches and the East River."
)
LES_NOTE = (
    "Taken as-is from the NYC DCP 2020 Neighborhood Tabulation Area "
    "'Lower East Side' (NTA2020 code MN0302), unmodified. Included "
    "in the study area as the Lower East Side immediately adjacent "
    "to Chinatown and Two Bridges, per the project's research scope."
)


def fetch_geojson(dataset: str, where: str, select: str) -> dict:
    resp = requests.get(
        f"https://data.cityofnewyork.us/resource/{dataset}.geojson",
        params={"$where": where, "$select": select, "$limit": 200},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def extend_point(x: float, y: float, dx: float, dy: float, dist: float) -> tuple[float, float]:
    length = (dx**2 + dy**2) ** 0.5
    return x + dx / length * dist, y + dy / length * dist


def build_division_st_cut_line() -> LineString:
    raw = fetch_geojson(
        CENTERLINE_DATASET,
        where="full_street_name='DIVISION ST' AND boroughcode='1'",
        select="physicalid,the_geom",
    )
    lines = [shape(f["geometry"]) for f in raw["features"]]
    merged = linemerge(unary_union(lines))
    if merged.geom_type != "LineString":
        raise RuntimeError(
            f"Expected Division St segments to merge into one LineString, got {merged.geom_type}. "
            "The street centerline data may have changed -- inspect before proceeding."
        )

    coords = list(merged.coords)
    (x0, y0), (x1, y1) = coords[0], coords[1]
    (xn1, yn1), (xn, yn) = coords[-2], coords[-1]
    west_pt = extend_point(x0, y0, x0 - x1, y0 - y1, EXTENSION_DEGREES)
    east_pt = extend_point(xn, yn, xn - xn1, yn - yn1, EXTENSION_DEGREES)
    return LineString([west_pt, *coords, east_pt])


def main() -> int:
    print("Fetching source NTA polygons...")
    nta = fetch_geojson(
        NTA_DATASET,
        where="ntaname='Chinatown-Two Bridges' OR ntaname='Lower East Side'",
        select="nta2020,ntaname,the_geom",
    )
    polys = {f["properties"]["ntaname"]: shape(f["geometry"]) for f in nta["features"]}
    if set(polys) != {"Chinatown-Two Bridges", "Lower East Side"}:
        raise RuntimeError(f"Expected exactly 2 source NTAs, got: {sorted(polys)}")

    print("Fetching Division St centerline and building the cut line...")
    cut_line = build_division_st_cut_line()

    print("Splitting Chinatown-Two Bridges along the cut line...")
    pieces = list(split(polys["Chinatown-Two Bridges"], cut_line).geoms)
    if len(pieces) != 2:
        raise RuntimeError(
            f"Expected the cut line to split the polygon into 2 pieces, got {len(pieces)}. "
            "Check EXTENSION_DEGREES and the source geometry before proceeding."
        )
    # North of the line (higher latitude) is Chinatown; south is Two Bridges.
    pieces.sort(key=lambda p: p.centroid.y, reverse=True)
    chinatown, two_bridges = pieces

    original_area = polys["Chinatown-Two Bridges"].area
    split_area = chinatown.area + two_bridges.area
    if abs(split_area - original_area) > original_area * 1e-6:
        raise RuntimeError(
            f"Split pieces' combined area ({split_area}) does not match the original "
            f"polygon's area ({original_area}) -- the split is not a clean partition."
        )

    def _feature(name: str, note: str, geom) -> dict:
        return {
            "type": "Feature",
            "properties": {"name": name, "definition_note": note},
            "geometry": mapping(geom),
        }

    features = [
        _feature("Chinatown", CHINATOWN_NOTE, chinatown),
        _feature("Two Bridges", TWO_BRIDGES_NOTE, two_bridges),
        _feature("Lower East Side", LES_NOTE, polys["Lower East Side"]),
    ]
    for feat in features:
        if not shape(feat["geometry"]).is_valid:
            raise RuntimeError(f"Produced an invalid geometry for {feat['properties']['name']}")

    collection = {"type": "FeatureCollection", "features": features}
    OUTPUT_PATH.write_text(json.dumps(collection, indent=2))
    print(f"Wrote {OUTPUT_PATH}")
    for feat in features:
        g = shape(feat["geometry"])
        print(f"  {feat['properties']['name']}: area {g.area:.8f} deg^2, valid={g.is_valid}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
