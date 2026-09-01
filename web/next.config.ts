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
  // With basePath set, the bare origin root is not a route at all, so
  // https://<deployment>.vercel.app/ returns a 404. That reads as a
  // broken deployment in three places that all request the root: the
  // Vercel dashboard's production card (it previews `/`, so the project
  // appears to have no working production deployment), the dashboard's
  // "Visit" button, and anyone who trims the URL. Redirecting the root to
  // the app costs nothing and removes that whole class of false alarm.
  // basePath: false is required -- redirect sources are themselves
  // prefixed with basePath otherwise, which would make this match
  // /division rather than /.
  async redirects() {
    return [{ source: "/", destination: basePath, permanent: false, basePath: false }];
  },
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
