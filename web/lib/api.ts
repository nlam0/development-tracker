/**
 * Typed fetch wrappers over api/ (M5). The frontend never calls
 * Socrata/Census/DOB directly -- every one of these hits FastAPI, which is
 * itself a read-only view over the ingested Postgres data (CLAUDE.md).
 *
 * Used from both server components (parcel pages) and client components
 * (feed, map, digest) -- NEXT_PUBLIC_API_URL must be reachable from
 * wherever `fetch` actually runs, which for a server component is the
 * Next.js server process, not the browser.
 */

import type {
  ActivityFeedResponse,
  MapFeatureCollection,
  Parcel,
  Permit,
  PropertyRecord,
  SortMode,
  StatsResponse,
  StudyAreaFeatureCollection,
} from "./types";
import type { FilterState } from "./filters";
import { filtersToSearchParams } from "./filters";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, params?: URLSearchParams): Promise<T> {
  const qs = params?.toString();
  const url = `${API_URL}${path}${qs ? `?${qs}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export { ApiError };

export function getActivity(
  filters: FilterState,
  opts: { sort?: SortMode; cursor?: string | null; limit?: number } = {},
): Promise<ActivityFeedResponse> {
  const params = filtersToSearchParams(filters);
  if (opts.sort) params.set("sort", opts.sort);
  if (opts.cursor) params.set("cursor", opts.cursor);
  if (opts.limit) params.set("limit", String(opts.limit));
  return request<ActivityFeedResponse>("/api/activity", params);
}

export function getMap(filters: FilterState): Promise<MapFeatureCollection> {
  return request<MapFeatureCollection>("/api/map", filtersToSearchParams(filters));
}

export function getStudyAreas(): Promise<StudyAreaFeatureCollection> {
  return request<StudyAreaFeatureCollection>("/api/study-areas");
}

export function getParcel(bbl: string): Promise<Parcel> {
  return request<Parcel>(`/api/parcels/${bbl}`);
}

export function getParcelPermits(bbl: string, limit = 100): Promise<Permit[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return request<Permit[]>(`/api/parcels/${bbl}/permits`, params);
}

export function getParcelRecords(bbl: string, limit = 100): Promise<PropertyRecord[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return request<PropertyRecord[]>(`/api/parcels/${bbl}/records`, params);
}

export function getStats(neighborhood?: string): Promise<StatsResponse> {
  const params = neighborhood ? new URLSearchParams({ neighborhood }) : undefined;
  return request<StatsResponse>("/api/stats", params);
}
