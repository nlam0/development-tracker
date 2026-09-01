import path from "node:path";
import type { NextConfig } from "next";

// Hosted at nicklam.co/division (a path under an existing personal site,
// not its own subdomain). Local dev is affected the same way: pages are
// at http://localhost:3000/division/... rather than the root.
const basePath = "/division";

const nextConfig: NextConfig = {
  basePath,
  // Next applies basePath automatically only to next/link and
  // next/navigation. Anything referenced as a plain string -- notably
  // files in public/ -- has to add the prefix itself, so the value is
  // exposed to client code here rather than hardcoded a second time at
  // the point of use. Hardcoding it is exactly how the MapLibre worker
  // URL in components/MapView.tsx silently broke when basePath was
  // introduced: the request 404'd to an HTML page, MapLibre's blob-worker
  // fallback hung on it, and the map rendered nothing but its background.
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
