"""Pydantic response models for api/routers/*.

Fields here match the canonical schema in db/migrations, not any upstream
Socrata field name -- CLAUDE.md's "source-specific vocabulary stops at the
adapter boundary" applies to the read side too. `raw` and `geom` are never
serialized: `raw` is an internal reprocessing aid, and `geom` is redundant
with the `latitude`/`longitude` columns every model below exposes instead.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class PermitOut(BaseModel):
    id: int
    source: str
    external_id: str
    bbl: str | None
    neighborhood: str | None
    study_area_match: str
    bin: str | None
    address: str | None
    filing_number: str | None
    permit_type: str | None
    work_type: str | None
    category: str
    filing_reason: str | None
    status: str | None
    description: str | None
    estimated_cost: float | None
    approved_date: date | None
    issued_date: date | None
    expired_date: date | None
    event_date: date
    latitude: float | None
    longitude: float | None
    owner_name: str | None
    retrieved_at: datetime
    # False once a full reload stops seeing this permit upstream (revoked,
    # superseded, or withdrawn). Surfaced rather than filtered: a permit
    # that disappears from DOB's published set is itself a research finding.
    is_current: bool


class ActivityFeedResponse(BaseModel):
    items: list[PermitOut]
    next_cursor: str | None


class ParcelPermitsResponse(BaseModel):
    """A page of a parcel's permits, with the count the page came from.

    `total` is not decoration: these endpoints default to 100 rows and one
    BBL in the study area carries 555 permits, so a caller that treated the
    returned list as complete under-reported eight parcels. Returning the
    total makes a partial page self-describing rather than something the
    caller has to already know to ask about.
    """

    items: list[PermitOut]
    total: int


class ParcelRecordsResponse(BaseModel):
    items: list["PropertyRecordOut"]
    total: int


class ParcelOut(BaseModel):
    bbl: str
    borough: int
    block: int
    lot: int
    address: str | None
    neighborhood: str | None
    latitude: float | None
    longitude: float | None
    zoning: str | None
    land_use: str | None
    lot_area: int | None
    building_area: int | None
    commercial_area: int | None
    residential_area: int | None
    units_residential: int | None
    units_total: int | None
    num_buildings: int | None
    num_floors: float | None
    year_built: int | None
    assessed_total: int | None
    owner_name: str | None
    census_tract_2020: str | None
    census_tract_2010: str | None
    pluto_version: str
    retrieved_at: datetime


class PropertyRecordOut(BaseModel):
    id: int
    source: str
    external_id: str
    document_id: str
    bbl: str | None
    bbl_confidence: str
    document_type: str
    document_label: str | None
    property_type: str | None
    recorded_date: date | None
    document_date: date | None
    amount: float | None
    parties: list[dict] | None
    retrieved_at: datetime


class GeoPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class MapFeatureProperties(BaseModel):
    id: int
    bbl: str | None
    neighborhood: str | None
    category: str
    address: str | None
    event_date: date
    estimated_cost: float | None


class MapFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeoPoint
    properties: MapFeatureProperties


class MapFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection plus the two counts the map needs to be honest.

    `total` and `truncated` are GeoJSON foreign members -- the spec permits
    them, and MapLibre ignores what it doesn't recognize, so this stays
    directly usable as a GeoJSON source. They exist because the endpoint
    caps its result set: without them a truncated response is
    indistinguishable from a complete one, and the map would silently
    present a subset of the study area as the whole of it.
    """

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[MapFeature]
    total: int
    truncated: bool


class StudyAreaProperties(BaseModel):
    name: str
    definition_note: str


class StudyAreaFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict
    properties: StudyAreaProperties


class StudyAreaFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[StudyAreaFeature]


class TopProject(BaseModel):
    id: int
    bbl: str | None
    address: str | None
    category: str
    estimated_cost: float
    event_date: date


class BlockActivity(BaseModel):
    block: str
    filings: int


class StatsWindow(BaseModel):
    window_days: int
    new_permits: int
    properties_with_activity: int
    total_estimated_cost: float
    new_building_permits: int
    demolition_permits: int
    largest_projects: list[TopProject]
    blocks_with_multiple_filings: list[BlockActivity]


class DataCoverage(BaseModel):
    """How far the ingested data actually reaches, and how fresh our copy is.

    These are different questions and the gap between them matters. DOB
    publishes a filing days after the fact, so `latest_event_date` trails
    today even when ingestion ran successfully this morning: a digest
    window ending today includes trailing dates the dataset has no
    coverage for yet. Reporting a count against those days without saying
    so overstates a slowdown that is really just reporting lag.
    """

    latest_event_date: date | None
    last_successful_ingest: datetime | None
    # Whole days between the newest permit on file and NYC today. The
    # trailing part of every window that is not yet covered.
    reporting_lag_days: int | None


class StatsResponse(BaseModel):
    generated_at: datetime
    study_area_note: str = (
        "Study-area boundaries are researcher-defined, not official city "
        "geography -- see /methodology."
    )
    coverage: DataCoverage
    windows: dict[str, StatsWindow]
