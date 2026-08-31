"use client";

import { addToWatchlist, removeFromWatchlist, useIsWatched, type WatchlistEntryType } from "@/lib/watchlist";

export default function WatchlistButton({
  type,
  value,
  label,
}: {
  type: WatchlistEntryType;
  value: string;
  label: string;
}) {
  const watched = useIsWatched(type, value);

  return (
    <button
      type="button"
      className="border border-border px-2 py-0.5 text-xs hover:bg-background"
      onClick={() => (watched ? removeFromWatchlist(type, value) : addToWatchlist(type, value, label))}
    >
      {watched ? "★ Watching" : "☆ Watch"}
    </button>
  );
}
