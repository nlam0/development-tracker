"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getActivity } from "@/lib/api";
import { filtersFromSearchParams } from "@/lib/filters";
import type { Permit, SortMode } from "@/lib/types";
import ActivityCard from "./ActivityCard";

const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "cost", label: "Estimated cost" },
];

export default function ActivityFeed() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = filtersFromSearchParams(searchParams);
  const sort = (searchParams.get("sort") as SortMode) || "newest";

  const [items, setItems] = useState<Permit[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filterKey = JSON.stringify(filters);

  useEffect(() => {
    let cancelled = false;
    // Marks the start of a new fetch triggered by a filter/sort change --
    // not state derivable from props, so the lint rule's usual "you might
    // not need an effect" case doesn't apply here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    getActivity(filters, { sort })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setCursor(res.next_cursor);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load activity");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, sort]);

  const loadMore = () => {
    if (!cursor) return;
    setLoadingMore(true);
    getActivity(filters, { sort, cursor })
      .then((res) => {
        setItems((prev) => [...prev, ...res.items]);
        setCursor(res.next_cursor);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load more"))
      .finally(() => setLoadingMore(false));
  };

  const setSort = (value: SortMode) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("sort", value);
    router.replace(`?${params.toString()}`);
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight">Development feed</h1>
        <label className="flex items-center gap-1.5 text-sm text-muted">
          Sort
          <select
            className="border border-border bg-background px-1.5 py-0.5"
            value={sort}
            onChange={(e) => setSort(e.target.value as SortMode)}
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="border border-border bg-surface p-3 text-sm text-red-700">{error}</p>}
      {loading && <p className="text-sm text-muted">Loading…</p>}
      {!loading && !error && items.length === 0 && (
        <p className="border border-border bg-surface p-3 text-sm text-muted">
          No activity matches the current filters.
        </p>
      )}

      <div className="flex flex-col gap-2">
        {items.map((permit) => (
          <ActivityCard key={`${permit.source}:${permit.id}`} permit={permit} />
        ))}
      </div>

      {cursor && (
        <button
          type="button"
          className="mt-3 border border-border px-3 py-1.5 text-sm hover:bg-surface disabled:opacity-50"
          onClick={loadMore}
          disabled={loadingMore}
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
