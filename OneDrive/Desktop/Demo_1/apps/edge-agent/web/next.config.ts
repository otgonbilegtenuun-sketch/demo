import type { NextConfig } from "next";

const backend = process.env.MERGEN_BACKEND_ORIGIN ?? "http://127.0.0.1:8080";

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd()
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/photos/:path*", destination: `${backend}/photos/:path*` },
      { source: "/clips/:path*", destination: `${backend}/clips/:path*` },
      { source: "/eval_clips/:path*", destination: `${backend}/eval_clips/:path*` },
      { source: "/video_feed", destination: `${backend}/video_feed` }
    ];
  }
};

export default nextConfig;
