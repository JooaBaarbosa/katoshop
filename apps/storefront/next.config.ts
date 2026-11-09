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
  images: {
    // Fotos servidas pelo catálogo através do gateway. Dentro do compose o host resolve para o
    // Traefik pelo alias de rede; fora dele, para o loopback.
    remotePatterns: [
      { protocol: "http", hostname: "api.katoshop.localhost", pathname: "/catalog/v1/media/**" },
    ],
    // O gateway da demo é sempre local (IP privado ou loopback), que o otimizador recusa por padrão.
    // O risco de SSRF fica contido: remotePatterns só aceita esse host e esse caminho.
    dangerouslyAllowLocalIP: true,
  },
};

export default nextConfig;
