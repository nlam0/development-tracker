export function formatCurrency(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(d);
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function blockFromBbl(bbl: string): string {
  return bbl.slice(1, 6);
}

/**
 * PLUTO's bct2020 field (parcels.census_tract_2020) packs borough(1) +
 * tract-whole(4, zero-padded) + split-suffix(2) with no separators, e.g.
 * "1002700" -> borough 1, tract 27.00. census_tract_2010 (ct2010) is
 * already ingested in the plain "N" / "N.NN" form this produces -- PLUTO
 * itself formats the two vintages differently, not a data error -- so
 * only the 2020 field needs decoding before display. Storage stays raw
 * (untouched here) since the exact bct2020 string is what a future ACS
 * join (M8) will need to match against.
 */
export function formatCensusTract2020(raw: string | null): string | null {
  if (!raw || raw.length !== 7) return raw;
  const whole = raw.slice(1, 5).replace(/^0+/, "") || "0";
  const suffix = raw.slice(5, 7);
  return suffix === "00" ? whole : `${whole}.${suffix}`;
}
