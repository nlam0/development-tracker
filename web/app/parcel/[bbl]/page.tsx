import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getParcel, getParcelPermits, getParcelRecords } from "@/lib/api";
import { blockFromBbl, formatCurrency, formatDate } from "@/lib/format";
import CategoryTag from "@/components/CategoryTag";
import WatchlistButton from "@/components/WatchlistButton";

export default async function ParcelPage(props: PageProps<"/parcel/[bbl]">) {
  const { bbl } = await props.params;

  let parcel;
  try {
    parcel = await getParcel(bbl);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const [permits, records] = await Promise.all([getParcelPermits(bbl), getParcelRecords(bbl)]);

  const block = blockFromBbl(bbl);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link href="/map" className="text-xs text-muted hover:text-foreground">
          ← Back to map
        </Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              {parcel.address ?? "Address unavailable"}
            </h1>
            <p className="font-mono text-sm text-muted">BBL {parcel.bbl}</p>
          </div>
          <div className="flex gap-2">
            <WatchlistButton
              type="parcel"
              value={parcel.bbl}
              label={parcel.address ?? parcel.bbl}
              actionLabel="this parcel"
            />
            <WatchlistButton
              type="block"
              value={block}
              label={`Block ${block}`}
              actionLabel={`block ${block}`}
            />
          </div>
        </div>
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
          Property
        </h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 border border-border bg-surface p-3 text-sm sm:grid-cols-3">
          <Field label="Land use" value={parcel.land_use} />
          <Field label="Zoning" value={parcel.zoning} />
          <Field label="Lot area" value={parcel.lot_area ? `${parcel.lot_area.toLocaleString()} sq ft` : null} />
          <Field
            label="Building area"
            value={parcel.building_area ? `${parcel.building_area.toLocaleString()} sq ft` : null}
          />
          <Field label="Year built" value={parcel.year_built} />
          <Field label="Residential units" value={parcel.units_residential} />
        </dl>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
          Recent development ({permits.length})
        </h2>
        {permits.length === 0 ? (
          <p className="border border-border bg-surface p-3 text-sm text-muted">
            No permits on record for this parcel.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {permits.map((permit) => (
              <div key={`${permit.source}:${permit.id}`} className="border border-border bg-surface p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{formatDate(permit.event_date)}</span>
                  <CategoryTag category={permit.category} />
                </div>
                {permit.description && <p className="mt-1 text-foreground/90">{permit.description}</p>}
                <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-muted">
                  {permit.work_type && <span>Work type: {permit.work_type}</span>}
                  <span>Est. cost: {formatCurrency(permit.estimated_cost)}</span>
                  {permit.status && <span>Status: {permit.status}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
          Property activity
        </h2>
        {records.length === 0 ? (
          <p className="border border-border bg-surface p-3 text-sm text-muted">
            No ACRIS transaction records loaded yet -- ACRIS ingestion is planned for a later
            milestone (see /methodology).
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {records.map((record) => (
              <div key={record.id} className="border border-border bg-surface p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">
                    {record.document_label ?? record.document_type}
                  </span>
                  <span className="text-muted">{formatDate(record.recorded_date)}</span>
                </div>
                {record.amount !== null && (
                  <p className="mt-1 text-xs text-muted">Amount: {formatCurrency(record.amount)}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Context</h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 border border-border bg-surface p-3 text-sm sm:grid-cols-3">
          <Field label="Neighborhood" value={parcel.neighborhood} />
          <Field label="Census tract (2020)" value={parcel.census_tract_2020} />
          <Field label="Census tract (2010)" value={parcel.census_tract_2010} />
        </dl>
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd>{value ?? "—"}</dd>
    </div>
  );
}
