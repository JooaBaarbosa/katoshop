import type { MetadataRoute } from "next";
import { siteUrl } from "../lib/env";
import { allCategories, allCollections, allProductSlugs } from "../lib/storefront";

export const revalidate = 3600;

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
