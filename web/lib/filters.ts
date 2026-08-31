/**
 * The one filter state object that drives both the feed and the map
 * (IMPLEMENTATION_PLAN.md M6: "One filter state object drives feed and
 * map"). It lives in the URL query string rather than React context, so
 * it survives navigation between / and /map, is shareable/bookmarkable,
 * and needs no separate state-management layer -- the query string *is*
 * the shared representation, read identically by both pages, and its
 * param names match api/filters.py's ActivityFilters field-for-field so
 * it can be forwarded to the API almost unchanged.
 */

import type { Category, Neighborhood, Source } from "./types";

export interface FilterState {
  neighborhood: Neighborhood[];
  category: Category[];
  source: Source[];
  block: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  costMin: number | null;
  costMax: number | null;
}

export const EMPTY_FILTERS: FilterState = {
  neighborhood: [],
  category: [],
  source: [],
  block: null,
  dateFrom: null,
  dateTo: null,
  costMin: null,
  costMax: null,
};

export const NEIGHBORHOODS: Neighborhood[] = ["Chinatown", "Two Bridges", "Lower East Side"];
export const CATEGORIES: Category[] = ["new_building", "alteration", "demolition", "other"];
export const SOURCES: Source[] = ["dob_now", "dob_legacy"];

export const CATEGORY_LABELS: Record<Category, string> = {
  new_building: "New building",
  alteration: "Alteration",
  demolition: "Demolition",
  other: "Other",
};

export const CATEGORY_COLORS: Record<Category, string> = {
  new_building: "#1a7f37",
  alteration: "#9a6700",
  demolition: "#cf222e",
  other: "#57606a",
};

export function filtersFromSearchParams(params: URLSearchParams): FilterState {
  const csv = (key: string) => {
    const v = params.get(key);
    return v ? v.split(",").filter(Boolean) : [];
  };
  const num = (key: string) => {
    const v = params.get(key);
    return v === null || v === "" ? null : Number(v);
  };
  return {
    neighborhood: csv("neighborhood") as Neighborhood[],
    category: csv("category") as Category[],
    source: csv("source") as Source[],
    block: params.get("block") || null,
    dateFrom: params.get("date_from") || null,
    dateTo: params.get("date_to") || null,
    costMin: num("cost_min"),
    costMax: num("cost_max"),
  };
}

/** Builds the query string api/filters.py expects -- shared by /api/activity and /api/map. */
export function filtersToSearchParams(filters: FilterState): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.neighborhood.length) params.set("neighborhood", filters.neighborhood.join(","));
  if (filters.category.length) params.set("category", filters.category.join(","));
  if (filters.source.length) params.set("source", filters.source.join(","));
  if (filters.block) params.set("block", filters.block);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.costMin !== null) params.set("cost_min", String(filters.costMin));
  if (filters.costMax !== null) params.set("cost_max", String(filters.costMax));
  return params;
}

export function hasActiveFilters(filters: FilterState): boolean {
  return (
    filters.neighborhood.length > 0 ||
    filters.category.length > 0 ||
    filters.source.length > 0 ||
    Boolean(filters.block) ||
    Boolean(filters.dateFrom) ||
    Boolean(filters.dateTo) ||
    filters.costMin !== null ||
    filters.costMax !== null
  );
}
