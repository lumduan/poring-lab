import type { NextConfig } from "next";

// `output: "standalone"` traces only the dependencies actually reached, for a small Docker image.
// The backend URL is deliberately NOT configured here: config is resolved at build time and would be
// baked into the image. src/app/page.tsx reads BACKEND_PUBLIC_URL per request instead.
const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
