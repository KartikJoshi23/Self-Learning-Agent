import type { NextConfig } from "next";

// Pure static export: the site is HTML, CSS, JS and JSON, served from Vercel's
// CDN with no server, no edge functions and nothing that can cost money. Every
// number it shows comes from public/data/*.json, written by
// scripts/export_site_data.py from the engine and the acceptance logs.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true, // /calibrated/ -> calibrated/index.html, so any static host serves it
  images: { unoptimized: true },
  reactStrictMode: true,
  // three.js and d3 are large; let Next tree-shake their entry points.
  experimental: { optimizePackageImports: ["three", "d3"] },
};

export default nextConfig;
