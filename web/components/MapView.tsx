"use client";

/**
 * MapLibre GL map for the interactive map view (PRD §7B). Renders the
 * study-area boundary (GET /api/study-areas -- see api/routers/map.py for
 * why that endpoint exists) and permits matching the current filters as a
 * clustered GeoJSON source, colored by category.
 *
 * Basemap: OpenFreeMap's "Positron" style (tiles.openfreemap.org), a free,
 * no-signup, no-API-key OSM-based vector style -- a light, muted basemap
 * that fits PRD §12's restrained visual direction. (MapLibre's own public
 * demo style at demotiles.maplibre.org was tried first, but it's a
 * world-map demo of country outlines with no tile data below country
 * zoom -- at this view's city-block zoom it rendered as nothing but its
 * flat background-color layer, a blank blue screen.) CLAUDE.md's
 * confirmed infrastructure names MapLibre GL JS but not a specific tile
 * provider, so this is still a default pending a deliberate choice --
 * swapping `MAP_STYLE_URL` is the only change needed if one is made.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { getMap, getStudyAreas } from "@/lib/api";
import { CATEGORY_COLORS } from "@/lib/filters";
import { filtersFromSearchParams } from "@/lib/filters";
import { formatCurrency, formatDate } from "@/lib/format";

const MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
// Center of the three study areas' combined bounding box (see
// pipeline/study_area/resolve.py's BBOX).
const STUDY_AREA_CENTER: [number, number] = [-73.987, 40.715];
const INITIAL_ZOOM = 14.5;
const MOVE_DEBOUNCE_MS = 250;

// maplibre-gl decodes vector tiles in a dedicated module Worker, whose URL
// it computes at runtime via a bundler-relative import. Turbopack doesn't
// resolve that correctly for this package -- the request falls through to
// Next's page router and comes back as HTML, which the browser refuses to
// run as a module script. Pointing it at a plain static copy (see
// scripts/copy-maplibre-worker.mjs, run on `npm install`) sidesteps the
// bundler entirely. Must run before any Map is constructed, so it's set
// at module scope rather than inside the component.
//
// The basePath prefix is required: public/ assets are served under it,
// but Next only auto-applies basePath to next/link and next/navigation,
// never to a plain string like this one. Without it the request 404s to
// an HTML page and MapLibre's blob-worker fallback hangs on that response
// instead of failing loudly -- the map then renders its background and
// nothing else, with no console error. next.config.ts owns the value.
maplibregl.setWorkerUrl(
  `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/maplibre/maplibre-gl-worker.mjs`,
);

// maplibre-gl's published types don't export an expression type to
// annotate this with -- it's passed straight into a paint spec below,
// which is where MapLibre itself validates its shape at runtime.
const CATEGORY_COLOR_EXPRESSION = [
  "match",
  ["get", "category"],
  "new_building",
  CATEGORY_COLORS.new_building,
  "alteration",
  CATEGORY_COLORS.alteration,
  "demolition",
  CATEGORY_COLORS.demolition,
  CATEGORY_COLORS.other,
] as unknown as maplibregl.DataDrivenPropertyValueSpecification<string>;

/**
 * Popup body for a spatially-matched permit, built as DOM nodes rather than
 * an HTML string.
 *
 * `address` reaches here from DOB's published records by way of our own
 * ingestion and API, none of which sanitize it -- it is stored and served as
 * received (permits.raw keeps the source record verbatim, by design). An
 * HTML string template would make any markup in an upstream address
 * executable in the page; setting .textContent cannot. No current address
 * contains markup, which is exactly why this is worth fixing now rather than
 * after one does.
 */
function popupContent(props: {
  address: string | null;
  category: string;
  event_date: string;
  estimated_cost: number | null;
}): HTMLElement {
  const root = document.createElement("div");
  root.style.fontSize = "12px";

  const address = document.createElement("strong");
  address.textContent = props.address ?? "Unknown address";

  const meta = document.createElement("div");
  meta.textContent = `${props.category} · ${formatDate(props.event_date)}`;

  const cost = document.createElement("div");
  cost.textContent = formatCurrency(props.estimated_cost);

  const caveat = document.createElement("em");
  caveat.textContent = "No parcel page -- matched by location, not BBL.";

  root.append(address, meta, cost, caveat);
  return root;
}

export default function MapView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = filtersFromSearchParams(searchParams);
  const filterKey = JSON.stringify(filters);

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const loadedRef = useRef(false);
  const moveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState<{ shown: number; total: number } | null>(null);

  /**
   * The viewport MapLibre is currently showing, as the API's bbox tuple.
   *
   * Returns null rather than a clamped guess when the viewport isn't a
   * well-formed box -- zoomed far out, getBounds() can report a span wider
   * than the world or one that wraps the antimeridian, and the API (rightly)
   * 422s on west >= east. Omitting bbox in that case asks for the whole
   * study area, which is the correct request at that zoom anyway.
   */
  const viewportBbox = useCallback((map: MapLibreMap): [number, number, number, number] | null => {
    const bounds = map.getBounds();
    const west = Math.max(bounds.getWest(), -180);
    const east = Math.min(bounds.getEast(), 180);
    const south = Math.max(bounds.getSouth(), -90);
    const north = Math.min(bounds.getNorth(), 90);
    if (west >= east || south >= north) return null;
    return [west, south, east, north];
  }, []);

  const refreshPermits = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    // Ask only for what's on screen. Unbounded, this endpoint caps at 5,000
    // of the study area's 10,364 permits; at any zoom where individual
    // markers are legible the viewport holds far fewer than that, so the
    // response is complete rather than a silent newest-first subset.
    getMap(filters, viewportBbox(map) ?? undefined)
      .then((collection) => {
        const source = map.getSource("permits") as maplibregl.GeoJSONSource | undefined;
        source?.setData(collection as unknown as GeoJSON.FeatureCollection);
        setTruncated(
          collection.truncated
            ? { shown: collection.features.length, total: collection.total }
            : null,
        );
      })
      .catch(() => {
        // Leave the last successfully loaded set on screen rather than
        // clearing markers on a transient fetch failure.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, viewportBbox]);

  // The map's "load" handler is registered once and closes over whatever
  // refreshPermits was current then; the moveend listener it installs has to
  // call today's version, with today's filters, so it goes through a ref.
  const refreshPermitsRef = useRef(refreshPermits);
  useEffect(() => {
    refreshPermitsRef.current = refreshPermits;
  }, [refreshPermits]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      center: STUDY_AREA_CENTER,
      zoom: INITIAL_ZOOM,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    // MapLibre swallows most load failures (a bad tile, a blocked sprite/
    // glyph request) internally and just renders less -- surface them
    // instead of leaving a silently-incomplete map on screen.
    map.on("error", (e: maplibregl.ErrorEvent) => {
      console.error("MapLibre error:", e.error);
      setMapError(e.error?.message ?? "Unknown map error");
    });

    map.on("load", () => {
      map.addSource("study-areas", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "study-area-boundary",
        type: "line",
        source: "study-areas",
        paint: { "line-color": "#17171a", "line-width": 1.5, "line-dasharray": [2, 2] },
      });

      map.addSource("permits", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterRadius: 40,
        clusterMaxZoom: 16,
      });

      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "permits",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#17171a",
          "circle-radius": ["step", ["get", "point_count"], 14, 10, 18, 50, 24],
          "circle-opacity": 0.85,
        },
      });
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "permits",
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 11,
          // Must name a font the style's glyph endpoint actually serves.
          // Omitting text-font falls back to the style spec's default
          // ["Open Sans Regular", "Arial Unicode MS Regular"], which
          // OpenFreeMap 404s -- MapLibre then renders these codepoints
          // locally instead, so labels still appear but bypass the glyph
          // pipeline entirely. Positron's own layers use Noto Sans, which
          // its endpoint serves. Revisit alongside MAP_STYLE_URL: this
          // name is only valid for a style whose glyphs provide it.
          "text-font": ["Noto Sans Regular"],
        },
        paint: { "text-color": "#ffffff" },
      });
      map.addLayer({
        id: "unclustered-point",
        type: "circle",
        source: "permits",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": CATEGORY_COLOR_EXPRESSION,
          "circle-radius": 6,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
        },
      });

      map.on("click", "clusters", (e: maplibregl.MapLayerMouseEvent) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ["clusters"] });
        const clusterId = features[0]?.properties?.cluster_id;
        const source = map.getSource("permits") as maplibregl.GeoJSONSource;
        if (clusterId === undefined) return;
        source.getClusterExpansionZoom(clusterId).then((zoom: number) => {
          const coords = (features[0].geometry as GeoJSON.Point).coordinates as [number, number];
          map.easeTo({ center: coords, zoom });
        });
      });

      map.on("click", "unclustered-point", (e: maplibregl.MapLayerMouseEvent) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const props = feature.properties as {
          bbl: string | null;
          address: string | null;
          category: string;
          event_date: string;
          estimated_cost: number | null;
        };
        if (props.bbl) {
          router.push(`/parcel/${props.bbl}`);
          return;
        }
        const coords = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
        new maplibregl.Popup().setLngLat(coords).setDOMContent(popupContent(props)).addTo(map);
      });

      for (const layer of ["clusters", "unclustered-point"]) {
        map.on("mouseenter", layer, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layer, () => {
          map.getCanvas().style.cursor = "";
        });
      }

      // Refetch for the new viewport once a pan/zoom settles. moveend fires
      // once per gesture, but a flicked pan can chain several; the debounce
      // keeps that to one request without making the map feel stale.
      map.on("moveend", () => {
        if (moveTimerRef.current) clearTimeout(moveTimerRef.current);
        moveTimerRef.current = setTimeout(() => refreshPermitsRef.current(), MOVE_DEBOUNCE_MS);
      });

      loadedRef.current = true;
      getStudyAreas()
        .then((collection) => {
          const source = map.getSource("study-areas") as maplibregl.GeoJSONSource;
          source?.setData(collection as unknown as GeoJSON.FeatureCollection);
        })
        .catch(() => {});
      refreshPermits();
    });

    return () => {
      if (moveTimerRef.current) clearTimeout(moveTimerRef.current);
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (loadedRef.current) refreshPermits();
  }, [refreshPermits]);

  return (
    <div className="relative">
      {mapError && (
        <p className="absolute top-2 left-2 z-10 max-w-md border border-red-700 bg-surface px-2 py-1 text-xs text-red-700">
          Map error: {mapError}
        </p>
      )}
      {truncated && (
        <p className="absolute bottom-2 left-2 z-10 max-w-md border border-border bg-surface px-2 py-1 text-xs text-muted">
          Showing the {truncated.shown.toLocaleString()} most recent of{" "}
          {truncated.total.toLocaleString()} matching permits. Zoom in to see all of them.
        </p>
      )}
      <div ref={containerRef} className="h-[70vh] w-full border border-border" />
    </div>
  );
}
