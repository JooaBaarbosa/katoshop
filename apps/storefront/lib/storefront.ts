import "server-only";
import type { CatalogComponents } from "@katoshop/api-client";
import { catalog, revalidate } from "./api";

export type PublicCategory = CatalogComponents["schemas"]["PublicCategory"];
export type Policies = CatalogComponents["schemas"]["Policies"];

/** Catálogo travado não pode segurar toda página (nem o healthcheck): desiste e usa o fallback. */
const CATALOG_TIMEOUT_MS = 2000;

/**
 * Prazo do lado da app, além do signal: o fetch com cache do Next não repassa o signal quando
 * revalida uma entrada vencida, e outras requisições da mesma chave esperam essa revalidação.
 */
function withDeadline<T>(call: (signal: AbortSignal) => Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error("catalog timeout")), CATALOG_TIMEOUT_MS);
  });
  return Promise.race([call(AbortSignal.timeout(CATALOG_TIMEOUT_MS)), deadline]).finally(() =>
    clearTimeout(timer),
  );
}

export const DEMO_NOTICE_FALLBACK = "Loja demonstrativa, nenhuma compra é real";

/** Categorias de primeiro nível para a navegação; vazio se o catálogo não responder. */
export async function navCategories(): Promise<PublicCategory[]> {
  try {
    const { data } = await withDeadline((signal) =>
      catalog().GET("/v1/categories", { fetch: revalidate(60), signal }),
    );
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
    const { data } = await withDeadline((signal) =>
      catalog().GET("/v1/storefront/settings", { fetch: revalidate(60), signal }),
    );
    return data?.policies ?? null;
  } catch {
    return null;
  }
}
