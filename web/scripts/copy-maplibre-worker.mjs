#!/usr/bin/env node
/**
 * maplibre-gl loads its tile-decoding Web Worker as `new Worker(url, {type:
 * "module"})`, with `url` computed at runtime via a bundler-relative import.
 * Turbopack (Next.js's dev bundler) doesn't resolve that URL correctly for
 * this package -- the request falls through to Next's page router instead
 * of a JS asset and comes back as HTML, which the browser then refuses to
 * run as a module script ("non-JavaScript MIME type of text/html").
 *
 * Fix: serve maplibre-gl's own prebuilt worker bundle as a plain static
 * asset from public/, and point maplibregl.setWorkerUrl() at it directly
 * (see components/MapView.tsx) -- bypassing the bundler's URL resolution
 * entirely. Run automatically on `npm install` (see package.json) so these
 * always match the installed maplibre-gl version rather than being
 * committed, hand-copied files that can drift out of sync with it.
 */

import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const srcDir = join(__dirname, "..", "node_modules", "maplibre-gl", "dist");
const destDir = join(__dirname, "..", "public", "maplibre");

// maplibre-gl-worker.mjs imports ./maplibre-gl-shared.mjs as a relative
// sibling -- both must be copied to the same relative paths for that
// import to resolve once served from public/.
const files = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

if (!existsSync(destDir)) mkdirSync(destDir, { recursive: true });

for (const file of files) {
  const src = join(srcDir, file);
  if (!existsSync(src)) {
    console.error(`copy-maplibre-worker: missing ${src} -- did the maplibre-gl version change?`);
    process.exit(1);
  }
  copyFileSync(src, join(destDir, file));
}

console.log(`copy-maplibre-worker: copied ${files.join(", ")} to public/maplibre/`);
