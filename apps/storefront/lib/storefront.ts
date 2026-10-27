import "server-only";
import type { CatalogComponents } from "@katoshop/api-client";
import { catalog, revalidate } from "./api";

export type PublicCategory = CatalogComponents["schemas"]["PublicCategory"];
export type Policies = CatalogComponents["schemas"]["Policies"];

export const DEMO_NOTICE_FALLBACK = "Loja demonstrativa, nenhuma compra é real";

/** Categorias de primeiro nível para a navegação; vazio se o catálogo não responder. */
export async function navCategories(): Promise<PublicCategory[]> {
  try {
    const { data } = await catalog().GET("/v1/categories", { fetch: revalidate(60) });
    return (data?.items ?? [])
      .filter((category) => category.parent_slug === null)
      .sort((a, b) => a.position - b.position);
  } catch {
    return [];
  }
}

/** Políticas da loja; null se ainda não configuradas (404) ou se o catálogo falhar. */
export async function storePolicies(): Promise<Policies | null> {
  try {
    const { data } = await catalog().GET("/v1/storefront/settings", { fetch: revalidate(60) });
    return data?.policies ?? null;
  } catch {
    return null;
  }
}
