import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@nexstudio/core"],
  webpack: (config) => {
    config.resolve ??= {};
    config.resolve.alias = {
      ...config.resolve.alias,
      "@nexstudio/db": path.resolve(__dirname, "../../packages/db/dist/index.js"),
      "@nexstudio/queues": path.resolve(__dirname, "../../packages/queues/dist/index.js"),
      "@valkey/valkey-glide": false
    };
    return config;
  }
};

export default nextConfig;
