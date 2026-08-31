import { Suspense } from "react";
import FilterBar from "@/components/FilterBar";
import ActivityFeed from "@/components/ActivityFeed";
import DigestPanel from "@/components/DigestPanel";

export default function FeedPage() {
  return (
    <div className="flex flex-col gap-4">
      <Suspense fallback={<div className="h-40 border border-border bg-surface" />}>
        <DigestPanel />
      </Suspense>
      <Suspense fallback={<div className="h-24 border border-border bg-surface" />}>
        <FilterBar />
      </Suspense>
      <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
        <ActivityFeed />
      </Suspense>
    </div>
  );
}
