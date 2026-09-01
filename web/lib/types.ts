/**
 * TypeScript mirrors of api/models.py's Pydantic response models.
 *
 * Field names and nullability match the FastAPI responses exactly -- keep
 * these two files in sync by hand; there's no shared schema generation
 * yet, and a drift here fails silently as `undefined` at render time
 * rather than as a type error.
 */

export type Category = "new_building" | "alteration" | "demolition" | "other";
export type Neighborhood = "Chinatown" | "Two Bridges" | "Lower East Side";
export type Source = "dob_now" | "dob_legacy";
export type SortMode = "newest" | "oldest" | "cost";

export interface Permit {
  id: number;
  source: string;
  external_id: string;
  bbl: string | null;
  neighborhood: string | null;
  study_area_match: "bbl" | "spatial";
  bin: string | null;
  address: string | null;
  filing_number: string | null;
  permit_type: string | null;
  work_type: string | null;
  category: Category;
  filing_reason: string | null;
  status: string | null;
  description: string | null;
  estimated_cost: number | null;
  approved_date: string | null;
  issued_date: string | null;
  expired_date: string | null;
  event_date: string;
  latitude: number | null;
  longitude: number | null;
  owner_name: string | null;
  retrieved_at: string;
  /** False once a full reload stops seeing this permit upstream. */
  is_current: boolean;
}

export interface ActivityFeedResponse {
  items: Permit[];
  next_cursor: string | null;
}

export interface Parcel {
  bbl: string;
  borough: number;
  block: number;
  lot: number;
  address: string | null;
  neighborhood: string | null;
  latitude: number | null;
  longitude: number | null;
  zoning: string | null;
  land_use: string | null;
  lot_area: number | null;
  building_area: number | null;
  commercial_area: number | null;
  residential_area: number | null;
  units_residential: number | null;
  units_total: number | null;
  num_buildings: number | null;
  num_floors: number | null;
  year_built: number | null;
  assessed_total: number | null;
  owner_name: string | null;
  census_tract_2020: string | null;
  census_tract_2010: string | null;
  pluto_version: string;
  retrieved_at: string;
}

export interface PropertyRecord {
  id: number;
  source: string;
  external_id: string;
  document_id: string;
  bbl: string | null;
  bbl_confidence: string;
  document_type: string;
  document_label: string | null;
  property_type: string | null;
  recorded_date: string | null;
  document_date: string | null;
  amount: number | null;
  parties: Record<string, unknown>[] | null;
  retrieved_at: string;
}

export interface MapFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    id: number;
    bbl: string | null;
    neighborhood: string | null;
    category: Category;
    address: string | null;
    event_date: string;
    estimated_cost: number | null;
  };
}

export interface MapFeatureCollection {
  type: "FeatureCollection";
  features: MapFeature[];
  /** Permits matching the filters (and viewport, if one was sent), before the server's cap. */
  total: number;
  /** True when `features` is a subset of `total` -- the map is not showing everything. */
  truncated: boolean;
}

export interface StudyAreaFeatureCollection {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "MultiPolygon"; coordinates: number[][][][] };
    properties: { name: string; definition_note: string };
  }[];
}

export interface TopProject {
  id: number;
  bbl: string | null;
  address: string | null;
  category: Category;
  estimated_cost: number;
  event_date: string;
}

export interface BlockActivity {
  block: string;
  filings: number;
}

export interface StatsWindow {
  window_days: number;
  new_permits: number;
  properties_with_activity: number;
  total_estimated_cost: number;
  new_building_permits: number;
  demolition_permits: number;
  largest_projects: TopProject[];
  blocks_with_multiple_filings: BlockActivity[];
}

export interface ParcelPermitsResponse {
  items: Permit[];
  /** All permits on this parcel, not just the returned page. */
  total: number;
}

export interface ParcelRecordsResponse {
  items: PropertyRecord[];
  total: number;
}

export interface DataCoverage {
  latest_event_date: string | null;
  last_successful_ingest: string | null;
  reporting_lag_days: number | null;
}

export interface StatsResponse {
  coverage: DataCoverage;
  generated_at: string;
  study_area_note: string;
  windows: Record<"7" | "30" | "90", StatsWindow>;
}
