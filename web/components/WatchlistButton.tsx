"use client";

import { addToWatchlist, removeFromWatchlist, useIsWatched, type WatchlistEntryType } from "@/lib/watchlist";

const DEFAULT_NOUN: Record<WatchlistEntryType, string> = {
  parcel: "parcel",
  block: "block",
  address: "address",
};

export default function WatchlistButton({
  type,
  value,
  label,
  actionLabel,
}: {
  type: WatchlistEntryType;
  value: string;
  label: string;
  /** What follows "Watch"/"Watching" in the button text, e.g. "block 00277".
   * Defaults to the bookmark type's name -- pass this when a page shows more
   * than one watch button at once, so they read as distinct actions rather
   * than duplicates (see app/parcel/[bbl]/page.tsx). */
  actionLabel?: string;
}) {
  const watched = useIsWatched(type, value);
  const noun = actionLabel ?? DEFAULT_NOUN[type];

  return (
    <button
      type="button"
      className="border border-border px-2 py-0.5 text-xs hover:bg-background"
      onClick={() => (watched ? removeFromWatchlist(type, value) : addToWatchlist(type, value, label))}
    >
      {watched ? `★ Watching ${noun}` : `☆ Watch ${noun}`}
    </button>
  );
}
