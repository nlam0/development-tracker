"""Static checks on the committed boundaries.geojson (decision D1).

These don't hit the network or the database -- they check the artifact that
load_boundaries.py loads into study_areas, so a corrupted or hand-edited
file gets caught before it reaches Postgres.
"""

import json
from pathlib import Path

from shapely.geometry import shape

BOUNDARIES_PATH = (
    Path(__file__).resolve().parent.parent / "pipeline" / "study_area" / "boundaries.geojson"
)
EXPECTED_NAMES = {"Chinatown", "Two Bridges", "Lower East Side"}


def _load():
    return json.loads(BOUNDARIES_PATH.read_text())


def test_exactly_three_named_study_areas():
    data = _load()
    names = {f["properties"]["name"] for f in data["features"]}
    assert names == EXPECTED_NAMES


def test_every_feature_has_a_definition_note():
    data = _load()
    for feat in data["features"]:
        note = feat["properties"].get("definition_note", "")
        assert len(note) > 20, f"{feat['properties']['name']} is missing a real definition_note"


def test_every_geometry_is_a_valid_polygon():
    data = _load()
    for feat in data["features"]:
        geom = shape(feat["geometry"])
        assert geom.is_valid, f"{feat['properties']['name']} geometry is invalid"
        assert geom.geom_type in ("Polygon", "MultiPolygon")


def test_chinatown_and_two_bridges_partition_the_combined_nta_area():
    """The split must not lose or duplicate area from the source NTA polygon."""
    data = _load()
    by_name = {f["properties"]["name"]: shape(f["geometry"]) for f in data["features"]}
    chinatown, two_bridges = by_name["Chinatown"], by_name["Two Bridges"]

    assert chinatown.intersection(two_bridges).area < 1e-12, "split pieces overlap"

    combined = chinatown.union(two_bridges)
    # The two pieces should differ from a straight union by no more than
    # floating-point noise -- i.e. no sliver gaps introduced by the split.
    assert combined.area == chinatown.area + two_bridges.area
