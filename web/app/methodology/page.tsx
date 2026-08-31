export const metadata = { title: "Methodology — Lower Manhattan Development Tracker" };

export default function MethodologyPage() {
  return (
    <div className="flex flex-col gap-6 text-sm leading-relaxed">
      <h1 className="text-lg font-semibold tracking-tight">Methodology</h1>

      <Section title="Why this exists">
        <p>
          This tool began as research infrastructure for a senior thesis studying neighborhood
          change in Chinatown and Two Bridges. NYC development information is spread across
          several independently structured public datasets -- DOB permits, PLUTO parcel data,
          ACRIS property records, Census ACS -- which makes repeated parcel-level research
          cumbersome. It combines those sources into one searchable interface and tracks new
          activity automatically, built for a single researcher rather than as a general-purpose
          real-estate platform.
        </p>
      </Section>

      <Section title="Study geography">
        <p>
          The study area covers <strong>Chinatown</strong>, <strong>Two Bridges</strong>, and the
          adjacent <strong>Lower East Side</strong>. These boundaries are researcher-defined, not
          official city administrative geography. They start from NYC&apos;s 2020 Neighborhood
          Tabulation Areas (NTA), with the combined official <code>Chinatown-Two Bridges</code>{" "}
          NTA hand-split along the Division Street centerline -- the conventional dividing line in
          local usage -- into separate Chinatown and Two Bridges areas; Lower East Side is taken
          as-is from its own NTA.
        </p>
        <p className="mt-2">
          Which parcels fall inside those boundaries is itself a judgment. Most are resolved by
          testing whether a PLUTO parcel&apos;s centroid falls inside a study-area polygon. A small
          number of parcels have no PLUTO centroid at all; those are admitted instead when their
          tax block unambiguously belongs to one study area (a weaker claim, recorded per parcel).
          Permits are matched the same way in principle: most by their parcel&apos;s BBL, and a
          small remainder -- lots the BBL allowlist can&apos;t reach, such as condo unit lots or
          merged/demapped lots -- by their own point falling inside a study-area polygon instead.
          A permit matched this second way has no parcel to attach to and so has no parcel page,
          even though it appears in the feed and on the map.
        </p>
      </Section>

      <Section title="Data sources">
        <ul className="list-disc pl-5">
          <li>
            <strong>DOB NOW</strong> (NYC Dept. of Buildings) -- current permit filings and their
            approval/issuance status.
          </li>
          <li>
            <strong>PLUTO</strong> (NYC Dept. of City Planning) -- parcel-level land use, zoning,
            building characteristics. A pinned, versioned snapshot, not a live feed.
          </li>
          <li>
            <strong>ACRIS</strong> (NYC Dept. of Finance) -- recorded property transactions
            (deeds, mortgages). Not yet loaded into this tool.
          </li>
          <li>
            <strong>Census ACS</strong> -- neighborhood-level demographic and housing context.
            Not yet loaded into this tool, and will never be attached to an individual parcel --
            only to a neighborhood as a whole.
          </li>
        </ul>
      </Section>

      <Section title="Update frequency">
        <p>
          Ingestion is intended to run once daily via a scheduled job. DOB NOW permits are fully
          reloaded on every run, since a permit&apos;s status can change after it first appears
          and re-scanning also catches newly-matchable spatial cases; PLUTO is a versioned
          snapshot reloaded as a whole when a new version is pinned. Every ingestion run is
          logged, and a run that fails is recorded as failed rather than silently skipped.
        </p>
      </Section>

      <Section title="How datasets are joined">
        <p>
          The Borough-Block-Lot number (<strong>BBL</strong>) is the primary key tying permits,
          parcels, and property records together. Each source keeps its own native record ID
          alongside the BBL for traceability back to the raw government record. Census data is
          joined at the census-tract level, never to an individual parcel.
        </p>
      </Section>

      <Section title="Permit categories">
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <CategoryDef term="New building" def="A filing for new construction on the lot." />
          <CategoryDef
            term="Alteration"
            def="A filing to modify an existing building -- the large majority of activity."
          />
          <CategoryDef term="Demolition" def="A filing for full demolition of a structure." />
          <CategoryDef
            term="Other"
            def={
              'Filings that don’t resolve to one of the three categories above (e.g. "No Work" filings).'
            }
          />
        </dl>
      </Section>

      <Section title="Known limitations">
        <ul className="list-disc pl-5">
          <li>Study-area boundaries are a researcher-drawn approximation, not official geography.</li>
          <li>
            A small number of parcels and permits are matched to the study area by a weaker method
            (block membership or point-in-polygon) than the primary centroid/BBL match; this is
            recorded per row rather than hidden.
          </li>
          <li>
            ACRIS property records and Census demographic context are not yet loaded -- parcel
            pages currently show permit history only.
          </li>
          <li>DOB legacy (pre-2016) permit history is not yet loaded.</li>
          <li>
            Estimated project costs are self-reported by filers at time of filing and are not
            independently verified.
          </li>
        </ul>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-1.5 text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
      {children}
    </section>
  );
}

function CategoryDef({ term, def }: { term: string; def: string }) {
  return (
    <div className="border border-border bg-surface p-2">
      <dt className="font-medium">{term}</dt>
      <dd className="text-muted">{def}</dd>
    </div>
  );
}
