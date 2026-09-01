import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hosted at nicklam.co/division (a path under an existing personal
  // site, not its own subdomain) -- basePath makes every Link/route/asset
  // Next.js generates resolve under /division automatically. Local dev
  // (`npm run dev`) is affected too: pages are at http://localhost:3000
  // /division/... rather than the root, matching the production path.
  basePath: "/division",
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
