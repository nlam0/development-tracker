import Link from "next/link";
import CategoryTag from "./CategoryTag";
import { formatCurrency, formatDate } from "@/lib/format";
import type { Permit } from "@/lib/types";

export default function ActivityCard({ permit }: { permit: Permit }) {
  const address = permit.address ?? "Address unavailable";
  return (
    <article className="border border-border bg-surface p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          {permit.bbl ? (
            <Link href={`/parcel/${permit.bbl}`} className="font-medium hover:underline">
              {address}
            </Link>
          ) : (
            <span className="font-medium" title="No parcel page: matched by location, not BBL">
              {address}
            </span>
          )}
          <div className="mt-0.5 text-xs text-muted">
            {permit.neighborhood ?? "Unknown neighborhood"} · {formatDate(permit.event_date)} ·{" "}
            {permit.source === "dob_now" ? "DOB NOW" : permit.source}
          </div>
        </div>
        <CategoryTag category={permit.category} />
      </div>

      {permit.description && (
        <p className="mt-2 line-clamp-2 text-sm text-foreground/90">{permit.description}</p>
      )}

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {permit.work_type && <span>Work type: {permit.work_type}</span>}
        <span>Est. cost: {formatCurrency(permit.estimated_cost)}</span>
        {permit.status && <span>Status: {permit.status}</span>}
      </div>
    </article>
  );
}
