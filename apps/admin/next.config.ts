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
  experimental: {
    // upload de fotos: uma foto por action, até 8 MB na API mais a folga do multipart
    // (o proxy.ts bufferiza até 10 MB por padrão, acima deste limite)
    serverActions: { bodySizeLimit: "9mb" },
  },
  images: {
    // Fotos servidas pelo catálogo através do gateway. Dentro do compose o host resolve para o
    // Traefik pelo alias de rede; fora dele, para o loopback.
    remotePatterns: [
      { protocol: "http", hostname: "api.katoshop.localhost", pathname: "/catalog/v1/media/**" },
    ],
    // O gateway local resolve para IP privado (Traefik) ou loopback, que o otimizador recusa por
    // padrão. Liberar só com IMAGES_ALLOW_LOCAL_IP=true (compose local), lido no BUILD: o
    // standalone congela esta config. Atenção: o otimizador segue redirects sem reaplicar
    // remotePatterns, então a rota de mídia do catálogo nunca pode redirecionar.
    dangerouslyAllowLocalIP: process.env.IMAGES_ALLOW_LOCAL_IP === "true",
  },
};

export default nextConfig;
