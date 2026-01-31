/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Enable standalone output for Docker deployment
  output: 'standalone',
  logging: {
    fetches: {
      fullUrl: true,
    },
  },
  async rewrites() {
    return [
      {
        // Allow /health to be accessed without /api prefix for backward compatibility
        source: '/health',
        destination: '/api/health',
      },
    ];
  },
};

module.exports = nextConfig; 