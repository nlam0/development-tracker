"use client";

/**
 * MapLibre GL map for the interactive map view (PRD §7B). Renders the
 * study-area boundary (GET /api/study-areas -- see api/routers/map.py for
 * why that endpoint exists) and permits matching the current filters as a
 * clustered GeoJSON source, colored by category.
 *
 * Basemap: MapLibre's own public demo style (demotiles.maplibre.org), a
 * bare OSM-derived vector style with no API key. CLAUDE.md's confirmed
 * infrastructure names MapLibre GL JS but not a specific tile provider, so
 * this is a placeholder pending a real basemap/key decision -- swapping
 * `MAP_STYLE_URL` is the only change needed once one is chosen.
 */

import { useCallback, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { getMap, getStudyAreas } from "@/lib/api";
import { CATEGORY_COLORS } from "@/lib/filters";
import { filtersFromSearchParams } from "@/lib/filters";
import { formatCurrency, formatDate } from "@/lib/format";

const MAP_STYLE_URL = "https://demotiles.maplibre.org/style.json";
// Center of the three study areas' combined bounding box (see
// pipeline/study_area/resolve.py's BBOX).
const STUDY_AREA_CENTER: [number, number] = [-73.987, 40.715];
const INITIAL_ZOOM = 14.5;

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

export default function MapView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = filtersFromSearchParams(searchParams);
  const filterKey = JSON.stringify(filters);

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const loadedRef = useRef(false);

  const refreshPermits = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    getMap(filters)
      .then((collection) => {
        const source = map.getSource("permits") as maplibregl.GeoJSONSource | undefined;
        source?.setData(collection as unknown as GeoJSON.FeatureCollection);
      })
      .catch(() => {
        // Leave the last successfully loaded set on screen rather than
        // clearing markers on a transient fetch failure.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey]);

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
        layout: { "text-field": "{point_count_abbreviated}", "text-size": 11 },
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
        new maplibregl.Popup()
          .setLngLat(coords)
          .setHTML(
            `<div style="font-size:12px">
              <strong>${props.address ?? "Unknown address"}</strong><br/>
              ${props.category} · ${formatDate(props.event_date)}<br/>
              ${formatCurrency(props.estimated_cost)}<br/>
              <em>No parcel page -- matched by location, not BBL.</em>
            </div>`,
          )
          .addTo(map);
      });

      for (const layer of ["clusters", "unclustered-point"]) {
        map.on("mouseenter", layer, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layer, () => {
          map.getCanvas().style.cursor = "";
        });
      }

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
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (loadedRef.current) refreshPermits();
  }, [refreshPermits]);

  return <div ref={containerRef} className="h-[70vh] w-full border border-border" />;
}
