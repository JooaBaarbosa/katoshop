import type { MetadataRoute } from "next";
import { siteUrl } from "../lib/env";

export default function robots(): MetadataRoute.Robots {
  const base = siteUrl();
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/conta", "/entrar", "/criar-conta", "/busca"] },
    sitemap: `${base}/sitemap.xml`,
  };
}
