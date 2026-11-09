import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "KatoShop",
    short_name: "KatoShop",
    description: "Loja demonstrativa de streetwear em tecido pesado.",
    start_url: "/",
    display: "standalone",
    theme_color: "#0E0E0E",
    background_color: "#0E0E0E",
    lang: "pt-BR",
    // O desenho do ícone ocupa a área toda, sem margem de segurança: só "any" (sem "maskable").
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
