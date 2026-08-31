"use client";

/**
 * Watchlist page (PRD §7D). Client-side only, backed by lib/watchlist.ts's
 * localStorage entries -- see that file for why "parcel" and "block"
 * entries get a real activity feed and "address" entries are a note
 * instead.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { getActivity, getParcelPermits } from "@/lib/api";
import { EMPTY_FILTERS } from "@/lib/filters";
import { formatCurrency, formatDate } from "@/lib/format";
import { removeFromWatchlist, useWatchlist, type WatchlistEntry } from "@/lib/watchlist";
import CategoryTag from "@/components/CategoryTag";
import type { Permit } from "@/lib/types";

function EntryActivity({ entry }: { entry: WatchlistEntry }) {
  const [permits, setPermits] = useState<Permit[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (entry.type === "parcel") {
      getParcelPermits(entry.value)
        .then(setPermits)
        .catch(() => setError(true));
    } else if (entry.type === "block") {
      getActivity({ ...EMPTY_FILTERS, block: entry.value }, { limit: 50 })
        .then((res) => setPermits(res.items))
        .catch(() => setError(true));
    }
  }, [entry.type, entry.value]);

  if (entry.type === "address") {
    return (
      <p className="text-xs text-muted">
        Free-text address bookmark -- no automatic activity match. Search the feed for this
        address manually.
      </p>
    );
  }
  if (error) return <p className="text-xs text-red-700">Failed to load activity.</p>;
  if (permits === null) return <p className="text-xs text-muted">Loading…</p>;
  if (permits.length === 0) return <p className="text-xs text-muted">No recent activity.</p>;

  return (
    <ul className="mt-2 flex flex-col gap-1.5">
      {permits.slice(0, 5).map((permit) => (
        <li key={`${permit.source}:${permit.id}`} className="flex items-center justify-between gap-2 text-xs">
          <span>
            {formatDate(permit.event_date)} · {permit.address ?? "Address unavailable"} ·{" "}
            {formatCurrency(permit.estimated_cost)}
          </span>
          <CategoryTag category={permit.category} />
        </li>
      ))}
    </ul>
  );
}

export default function WatchlistPage() {
  const entries = useWatchlist();

  const remove = (entry: WatchlistEntry) => {
    removeFromWatchlist(entry.type, entry.value);
  };

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold tracking-tight">Watchlist</h1>
      <p className="text-sm text-muted">
        Saved locally in this browser -- no account, no sync. Watch a parcel or block from its
        parcel page.
      </p>

      {entries.length === 0 ? (
        <p className="border border-border bg-surface p-3 text-sm text-muted">
          Nothing watched yet. Visit a{" "}
          <Link href="/" className="underline">
            parcel from the feed
          </Link>{" "}
          and click &ldquo;Watch&rdquo;.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {entries.map((entry) => (
            <div key={entry.id} className="border border-border bg-surface p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="text-xs uppercase tracking-wide text-muted">{entry.type}</span>
                  {entry.type === "parcel" ? (
                    <Link href={`/parcel/${entry.value}`} className="block font-medium hover:underline">
                      {entry.label}
                    </Link>
                  ) : (
                    <div className="font-medium">{entry.label}</div>
                  )}
                </div>
                <button
                  type="button"
                  className="text-xs text-muted underline hover:text-foreground"
                  onClick={() => remove(entry)}
                >
                  Remove
                </button>
              </div>
              <EntryActivity entry={entry} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
