/**
 * The watchlist is client-side only -- no auth or backend persistence in
 * V1 (CLAUDE.md, PRD §7D). Backed by localStorage, so it's private to one
 * browser and gone if storage is cleared; that tradeoff is what "no auth
 * required" buys.
 *
 * Three bookmark types, matching what the API can actually resolve into
 * an activity view:
 *  - "parcel": a BBL. Real activity via GET /api/parcels/{bbl}/permits.
 *  - "block":  a 5-digit BBL block. Real activity via
 *              GET /api/activity?block=... (api/filters.py).
 *  - "address": a free-text label with no BBL. There is no address-search
 *    endpoint -- R2 in IMPLEMENTATION_PLAN.md deliberately did not build
 *    fuzzy address matching, since D7(b)'s spatial fallback already
 *    covers what address matching would have. An address bookmark is
 *    therefore a note, not a live feed; the watchlist page says so rather
 *    than silently showing nothing.
 */

import { useSyncExternalStore } from "react";

export type WatchlistEntryType = "parcel" | "block" | "address";

export interface WatchlistEntry {
  id: string;
  type: WatchlistEntryType;
  value: string;
  label: string;
  addedAt: string;
}

const STORAGE_KEY = "development-tracker:watchlist";

function readAll(): WatchlistEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as WatchlistEntry[]) : [];
  } catch {
    return [];
  }
}

function writeAll(entries: WatchlistEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Storage unavailable (private browsing, quota) -- fail silently; the
    // watchlist is a convenience feature, not a system of record.
  }
  notify();
}

// A minimal pub-sub so every WatchlistButton and the watchlist page itself
// re-render off the same source of truth via useSyncExternalStore, rather
// than each holding its own useState+useEffect copy that only syncs on
// mount -- that pattern also can't reflect a change made by a *different*
// mounted button for the same entry without a page reload.
type Listener = () => void;
const listeners = new Set<Listener>();

// useSyncExternalStore requires getSnapshot to return a cached, stable
// reference when nothing has changed -- a fresh array (even with
// identical contents) on every call reads as "changed" on every render
// and triggers React's infinite-loop guard ("The result of getSnapshot
// should be cached"). This cache is invalidated only on an actual write.
let cachedWatchlist: WatchlistEntry[] | null = null;

function notify(): void {
  cachedWatchlist = null;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getWatchlist(): WatchlistEntry[] {
  if (cachedWatchlist === null) {
    cachedWatchlist = readAll().sort((a, b) => b.addedAt.localeCompare(a.addedAt));
  }
  return cachedWatchlist;
}

export function isWatched(type: WatchlistEntryType, value: string): boolean {
  return readAll().some((e) => e.type === type && e.value === value);
}

export function addToWatchlist(type: WatchlistEntryType, value: string, label: string): void {
  const entries = readAll();
  if (entries.some((e) => e.type === type && e.value === value)) return;
  entries.push({
    id: `${type}:${value}`,
    type,
    value,
    label,
    addedAt: new Date().toISOString(),
  });
  writeAll(entries);
}

export function removeFromWatchlist(type: WatchlistEntryType, value: string): void {
  writeAll(readAll().filter((e) => !(e.type === type && e.value === value)));
}

const EMPTY: WatchlistEntry[] = [];

export function useWatchlist(): WatchlistEntry[] {
  return useSyncExternalStore(subscribe, getWatchlist, () => EMPTY);
}

export function useIsWatched(type: WatchlistEntryType, value: string): boolean {
  return useSyncExternalStore(
    subscribe,
    () => isWatched(type, value),
    () => false,
  );
}
