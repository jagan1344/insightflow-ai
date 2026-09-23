/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/ws", destination: `${backend}/ws` },
    ];
  },
};

module.exports = nextConfig;
