import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true, // For static export if needed
  },
  // Enable standalone output for Docker deployment
  output: 'standalone',
  experimental: {
    // Add any experimental features here if needed
  },
};

export default nextConfig;
