import { Suspense } from "react";
import FilterBar from "@/components/FilterBar";
import MapView from "@/components/MapView";

export default function MapPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold tracking-tight">Map</h1>
      <Suspense fallback={<div className="h-24 border border-border bg-surface" />}>
        <FilterBar />
      </Suspense>
      <Suspense fallback={<div className="h-[70vh] w-full border border-border bg-surface" />}>
        <MapView />
      </Suspense>
    </div>
  );
}
