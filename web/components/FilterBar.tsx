"use client";

/**
 * Shared filter controls for the feed and the map (PRD §7A/§7B). Reads and
 * writes the URL search string via lib/filters.ts, so this component
 * renders identically -- and stays in sync -- on both / and /map without
 * any state lifted between them.
 */

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  CATEGORIES,
  CATEGORY_LABELS,
  EMPTY_FILTERS,
  filtersFromSearchParams,
  filtersToSearchParams,
  hasActiveFilters,
  NEIGHBORHOODS,
  SOURCES,
  type FilterState,
} from "@/lib/filters";
import type { Category, Neighborhood, Source } from "@/lib/types";

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

const FILTER_PARAM_KEYS = [
  "neighborhood",
  "category",
  "source",
  "block",
  "date_from",
  "date_to",
  "cost_min",
  "cost_max",
];

export default function FilterBar() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlFilters = filtersFromSearchParams(searchParams);

  // Not wrapped in useCallback: React Compiler auto-memoizes where it's
  // beneficial, and manual memoization here couldn't be preserved across
  // the compiler's transform anyway (it depends on iterating the foreign
  // ReadonlyURLSearchParams instance from useSearchParams).
  const commit = (next: FilterState) => {
    const params = filtersToSearchParams(next);
    // Preserve non-filter params the page already has (e.g. `sort`, which
    // is feed-only and doesn't live in FilterState) -- changing a filter
    // shouldn't reset those.
    searchParams.forEach((value, key) => {
      if (!FILTER_PARAM_KEYS.includes(key)) params.set(key, value);
    });
    router.replace(`${pathname}?${params.toString()}`);
  };

  return (
    <div className="border border-border bg-surface p-4 text-sm">
      <div className="flex flex-wrap gap-8">
        <fieldset>
          <legend className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">
            Neighborhood
          </legend>
          <div className="flex flex-col gap-1">
            {NEIGHBORHOODS.map((n: Neighborhood) => (
              <label key={n} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={urlFilters.neighborhood.includes(n)}
                  onChange={() =>
                    commit({ ...urlFilters, neighborhood: toggle(urlFilters.neighborhood, n) })
                  }
                />
                {n}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">
            Category
          </legend>
          <div className="flex flex-col gap-1">
            {CATEGORIES.map((c: Category) => (
              <label key={c} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={urlFilters.category.includes(c)}
                  onChange={() =>
                    commit({ ...urlFilters, category: toggle(urlFilters.category, c) })
                  }
                />
                {CATEGORY_LABELS[c]}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">
            Source
          </legend>
          <div className="flex flex-col gap-1">
            {SOURCES.map((s: Source) => (
              <label key={s} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={urlFilters.source.includes(s)}
                  onChange={() => commit({ ...urlFilters, source: toggle(urlFilters.source, s) })}
                />
                {s === "dob_now" ? "DOB NOW" : "DOB legacy"}
              </label>
            ))}
          </div>
        </fieldset>

        {/* Keyed by the URL's filter portion so a change that originates
            outside this component (Clear filters, browser back/forward)
            remounts these fields with fresh initial values, instead of a
            useEffect resyncing local draft state from a changed prop. */}
        <RangeInputs
          key={filtersToSearchParams(urlFilters).toString()}
          initial={urlFilters}
          onCommit={commit}
        />

        {hasActiveFilters(urlFilters) && (
          <button
            type="button"
            className="self-start text-xs text-muted underline hover:text-foreground"
            onClick={() => commit(EMPTY_FILTERS)}
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Date/cost inputs need local draft state so typing doesn't push a URL
 * update per keystroke -- they commit on blur instead. Isolated into its
 * own component (see the `key` at the call site) so that draft state
 * resets by remounting rather than by an effect syncing it from props.
 */
function RangeInputs({
  initial,
  onCommit,
}: {
  initial: FilterState;
  onCommit: (next: FilterState) => void;
}) {
  const [draft, setDraft] = useState(initial);
  const commitDraft = () => onCommit(draft);

  return (
    <>
      <fieldset>
        <legend className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">
          Date range
        </legend>
        <div className="flex flex-col gap-1">
          <input
            type="date"
            className="border border-border bg-background px-1.5 py-0.5"
            value={draft.dateFrom ?? ""}
            onChange={(e) => setDraft({ ...draft, dateFrom: e.target.value || null })}
            onBlur={commitDraft}
          />
          <input
            type="date"
            className="border border-border bg-background px-1.5 py-0.5"
            value={draft.dateTo ?? ""}
            onChange={(e) => setDraft({ ...draft, dateTo: e.target.value || null })}
            onBlur={commitDraft}
          />
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">
          Estimated cost ($)
        </legend>
        <div className="flex flex-col gap-1">
          <input
            type="number"
            min={0}
            placeholder="Min"
            className="w-28 border border-border bg-background px-1.5 py-0.5"
            value={draft.costMin ?? ""}
            onChange={(e) =>
              setDraft({ ...draft, costMin: e.target.value === "" ? null : Number(e.target.value) })
            }
            onBlur={commitDraft}
          />
          <input
            type="number"
            min={0}
            placeholder="Max"
            className="w-28 border border-border bg-background px-1.5 py-0.5"
            value={draft.costMax ?? ""}
            onChange={(e) =>
              setDraft({ ...draft, costMax: e.target.value === "" ? null : Number(e.target.value) })
            }
            onBlur={commitDraft}
          />
        </div>
      </fieldset>
    </>
  );
}
