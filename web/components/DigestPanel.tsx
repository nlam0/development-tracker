"use client";

/**
 * Research digest (PRD §7E). The architecture sketch in
 * IMPLEMENTATION_PLAN.md doesn't give this its own route, so it lives as a
 * panel on the feed -- the landing page -- rather than inventing a page
 * the plan never called for.
 */

import { useEffect, useState } from "react";
import { getStats } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { StatsResponse } from "@/lib/types";

const WINDOWS: ("7" | "30" | "90")[] = ["7", "30", "90"];

/**
 * One sentence stating how much of each window the data actually covers.
 *
 * DOB publishes filings several days after the fact, so the most recent
 * days of any window are systematically empty -- not quiet. Without this,
 * "13 permits in the past 7 days" reads as a 7-day observation when it is
 * closer to a 3-day one, and a researcher would draw a trend from the
 * reporting pipeline rather than from the neighborhood.
 */
function coverageNote(stats: StatsResponse): string | null {
  const { latest_event_date, reporting_lag_days } = stats.coverage;
  if (!latest_event_date || reporting_lag_days === null) return null;
  if (reporting_lag_days <= 0) return `Permit data current through ${latest_event_date}.`;
  const days = reporting_lag_days === 1 ? "day" : "days";
  return (
    `Permit data current through ${latest_event_date} -- ` +
    `the most recent ${reporting_lag_days} ${days} are not yet reported by DOB, ` +
    `so each window counts fewer days than it names.`
  );
}

function digestText(stats: StatsResponse): string {
  const lines = [`Development activity digest -- generated ${stats.generated_at}`];
  const coverage = coverageNote(stats);
  if (coverage) lines.push(coverage);
  lines.push("");
  for (const w of WINDOWS) {
    const win = stats.windows[w];
    lines.push(
      `Past ${w} days: ${win.new_permits} new permits, ${win.properties_with_activity} properties active, ` +
        `${formatCurrency(win.total_estimated_cost)} total estimated cost, ` +
        `${win.new_building_permits} new building, ${win.demolition_permits} demolition.`,
    );
    if (win.largest_projects.length) {
      lines.push(
        `  Largest: ${win.largest_projects
          .map((p) => `${p.address ?? p.bbl} (${formatCurrency(p.estimated_cost)})`)
          .join("; ")}`,
      );
    }
  }
  return lines.join("\n");
}

export default function DigestPanel() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load digest"));
  }, []);

  const copy = async () => {
    if (!stats) return;
    try {
      await navigator.clipboard.writeText(digestText(stats));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable (e.g. insecure context) -- nothing to
      // recover into; the button simply won't confirm a copy.
    }
  };

  if (error) return null;
  if (!stats) return <p className="text-xs text-muted">Loading digest…</p>;

  return (
    <div className="border border-border bg-surface p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight">Research digest</h2>
        <button
          type="button"
          className="border border-border px-2 py-0.5 text-xs hover:bg-background"
          onClick={copy}
        >
          {copied ? "Copied" : "Copy summary"}
        </button>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {WINDOWS.map((w) => {
          const win = stats.windows[w];
          return (
            <div key={w} className="border border-border p-2 text-sm">
              <div className="text-xs font-medium uppercase tracking-wide text-muted">
                Past {w} days
              </div>
              <div className="mt-1">{win.new_permits} new permits</div>
              <div>{win.properties_with_activity} properties active</div>
              <div>{formatCurrency(win.total_estimated_cost)} total est. cost</div>
              <div>{win.new_building_permits} new building</div>
              <div>{win.demolition_permits} demolition</div>
            </div>
          );
        })}
      </div>
      {coverageNote(stats) && <p className="mt-2 text-xs text-muted">{coverageNote(stats)}</p>}
      <p className="mt-1 text-xs text-muted">{stats.study_area_note}</p>
    </div>
  );
}
