import type { MetadataRoute } from "next";
import { siteUrl } from "../lib/env";
import { allCategories, allCollections, allProductSlugs } from "../lib/storefront";

// Ruling R21: renderização por requisição (o build não alcança o catálogo e congelaria o
// fallback). A revalidação de 60 s fica na camada de dados: cada fetch usa next.revalidate = 60.
export const dynamic = "force-dynamic";
// Erro do catálogo durante a paginação lança (resposta 500), nunca um sitemap truncado.

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = siteUrl();
  const [categories, collections, products] = await Promise.all([
    allCategories(),
    allCollections(),
    allProductSlugs(),
  ]);
  return [
    { url: `${base}/`, changeFrequency: "daily", priority: 1 },
    ...categories.map((category) => ({
      url: `${base}/c/${category.slug}`,
      changeFrequency: "daily" as const,
      priority: 0.8,
    })),
    ...collections.map((collection) => ({
      url: `${base}/colecoes/${collection.slug}`,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    })),
    ...products.map((slug) => ({
      url: `${base}/p/${slug}`,
      changeFrequency: "weekly" as const,
      priority: 0.6,
    })),
  ];
}
