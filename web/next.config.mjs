/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  images: {
    localPatterns: [
      {
        pathname: "/api/artifacts"
      }
    ],
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 3600
  }
};

export default nextConfig;
