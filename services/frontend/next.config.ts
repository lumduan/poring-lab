import type { NextConfig } from "next";

// `output: "standalone"` traces only the dependencies actually reached, for a small Docker image.
// The backend URL is deliberately NOT configured here: config is resolved at build time and would be
// baked into the image. src/app/page.tsx reads BACKEND_PUBLIC_URL per request instead.
//
// allowedDevOrigins: `next dev` refuses dev assets to hosts other than the one it started on. The
// frontend-dev container (compose.dev.yaml) is opened at http://HOST_LAN_IP:3000. Dev only.
const devHost = process.env.HOST_LAN_IP;

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  ...(devHost ? { allowedDevOrigins: [devHost] } : {}),
};

export default nextConfig;
