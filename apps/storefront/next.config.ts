import path from "node:path";
import type { NextConfig } from "next";

// raiz do monorepo: o standalone precisa rastrear os pacotes do workspace
const repoRoot = path.resolve(process.cwd(), "../..");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: repoRoot,
  turbopack: { root: repoRoot },
  transpilePackages: ["@katoshop/ui", "@katoshop/api-client"],
  poweredByHeader: false,
};

export default nextConfig;
