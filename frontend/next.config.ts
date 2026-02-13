import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true, // For static export if needed
  },
  // Enable standalone output for Docker deployment
  output: 'standalone',
  // Prevent aggressive caching of HTML so production gets latest UI after deploy
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-cache, no-store, must-revalidate',
          },
        ],
      },
    ];
  },
  experimental: {
    // Add any experimental features here if needed
  },
};

export default nextConfig;
