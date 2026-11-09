import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets the dev server be opened at http://resqivo.localhost:3000 (a loopback
  // alias); Next blocks dev assets for unlisted hosts.
  allowedDevOrigins: ["resqivo.localhost"],
};

export default nextConfig;
