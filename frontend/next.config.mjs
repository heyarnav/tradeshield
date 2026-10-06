/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5001/api",
  },
  // Next 16 refuses dev resources (HMR socket, client chunks) from any host
  // other than localhost, so opening the dev server as 127.0.0.1 or via the LAN
  // IP silently disables hydration and every button stops responding.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
