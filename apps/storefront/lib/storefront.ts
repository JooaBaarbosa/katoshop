import "server-only";
import type { CatalogComponents } from "@katoshop/api-client";
import { catalog, revalidate } from "./api";
import { apiUrl } from "./env";
import type { CatalogFilters } from "./filters";
import type { ProductDetail } from "./pdp";

type Schemas = CatalogComponents["schemas"];
export type PublicCategory = Schemas["PublicCategory"];
export type PublicCollection = Schemas["PublicCollection"];
export type Policies = Schemas["Policies"];
export type StorefrontSettings = Schemas["StorefrontSettings"];
export type ProductCard = Schemas["ProductCardOut"];
export type ProductCardPage = Schemas["ProductCardPage"];
export type Facets = Schemas["FacetsOut"];

/** Resultado de uma chamada ao catálogo que a página precisa distinguir. */
export type Fetched<T> =
  | { ok: true; data: T }
  | { ok: false; reason: "not_found" | "invalid" | "unavailable" };

/** Recorte fixo da listagem, vindo da rota (não da URL de filtros). */
export type ListingScope = { category?: string; collection?: string };

const REVALIDATE_SECONDS = 60;
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

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
  return (await allCategories())
    .filter((category) => category.parent_slug === null)
    .sort((a, b) => a.position - b.position);
}

/** Configurações da vitrine; null se ainda não configuradas (404) ou se o catálogo falhar. */
export async function storeSettings(): Promise<StorefrontSettings | null> {
  try {
    const { data } = await withDeadline((signal) =>
      catalog().GET("/v1/storefront/settings", { fetch: revalidate(REVALIDATE_SECONDS), signal }),
    );
    return data ?? null;
  } catch {
    return null;
  }
}

/** Políticas da loja; null se ainda não configuradas (404) ou se o catálogo falhar. */
export async function storePolicies(): Promise<Policies | null> {
  return (await storeSettings())?.policies ?? null;
}

/** Todas as categorias (inclusive subcategorias); vazio se o catálogo não responder. */
export async function allCategories(): Promise<PublicCategory[]> {
  const result = await categoryList();
  return result.ok ? result.data : [];
}

/** Coleções publicadas; vazio se o catálogo não responder. */
export async function allCollections(): Promise<PublicCollection[]> {
  try {
    const { data } = await withDeadline((signal) =>
      catalog().GET("/v1/collections", { fetch: revalidate(REVALIDATE_SECONDS), signal }),
    );
    return data?.items ?? [];
  } catch {
    return [];
  }
}

function failure(status: number): { ok: false; reason: "not_found" | "invalid" | "unavailable" } {
  if (status === 404) return { ok: false, reason: "not_found" };
  if (status === 422) return { ok: false, reason: "invalid" };
  return { ok: false, reason: "unavailable" };
}

async function fetched<T>(
  call: (signal: AbortSignal) => Promise<{ data?: T; response: Response }>,
): Promise<Fetched<T>> {
  try {
    const { data, response } = await withDeadline(call);
    return response.ok && data !== undefined ? { ok: true, data } : failure(response.status);
  } catch {
    return { ok: false, reason: "unavailable" };
  }
}

function categoryList(): Promise<Fetched<PublicCategory[]>> {
  return fetched(async (signal) => {
    const { data, response } = await catalog().GET("/v1/categories", {
      fetch: revalidate(REVALIDATE_SECONDS),
      signal,
    });
    return { data: data?.items, response };
  });
}

/**
 * Categoria pelo slug. `not_found` só quando a lista carregou e o slug não está nela;
 * catálogo fora do ar é `unavailable` (a página lança e cai na página de erro, não em 404).
 */
export async function categoryBySlug(slug: string): Promise<Fetched<PublicCategory>> {
  const result = await categoryList();
  if (!result.ok) return { ok: false, reason: "unavailable" };
  const category = result.data.find((c) => c.slug === slug);
  return category ? { ok: true, data: category } : { ok: false, reason: "not_found" };
}

export async function collectionBySlug(slug: string): Promise<Fetched<PublicCollection>> {
  if (!SLUG.test(slug) || slug.length > 120) return { ok: false, reason: "not_found" };
  return fetched((signal) =>
    catalog().GET("/v1/collections/{slug}", {
      params: { path: { slug } },
      fetch: revalidate(REVALIDATE_SECONDS),
      signal,
    }),
  );
}

export async function productDetail(slug: string): Promise<Fetched<ProductDetail>> {
  if (!SLUG.test(slug) || slug.length > 160) return { ok: false, reason: "not_found" };
  return fetched((signal) =>
    catalog().GET("/v1/products/{slug}", {
      params: { path: { slug } },
      fetch: revalidate(REVALIDATE_SECONDS),
      signal,
    }),
  );
}

/** Query da API (preço em centavos, nomes da API) para um recorte com filtros da loja. */
export function apiQuery(scope: ListingScope, f: CatalogFilters) {
  return {
    ...(scope.category !== undefined ? { category: scope.category } : {}),
    ...(scope.collection !== undefined ? { collection: scope.collection } : {}),
    size: f.size,
    color: f.color,
    ...(f.priceMin !== undefined ? { price_min: f.priceMin } : {}),
    ...(f.priceMax !== undefined ? { price_max: f.priceMax } : {}),
    sort: f.sort,
    ...(f.q !== undefined ? { q: f.q } : {}),
  };
}

export async function listProducts(
  scope: ListingScope,
  f: CatalogFilters,
  cursor?: string,
  limit = 24,
): Promise<Fetched<ProductCardPage>> {
  return fetched((signal) =>
    catalog().GET("/v1/products", {
      params: { query: { ...apiQuery(scope, f), ...(cursor ? { cursor } : {}), limit } },
      fetch: revalidate(REVALIDATE_SECONDS),
      signal,
    }),
  );
}

/** Contadores das facetas; null quando o filtro é inválido ou o catálogo falha. */
export async function productFacets(scope: ListingScope, f: CatalogFilters): Promise<Facets | null> {
  const result = await fetched((signal) =>
    catalog().GET("/v1/products/facets", {
      params: { query: apiQuery(scope, f) },
      fetch: revalidate(REVALIDATE_SECONDS),
      signal,
    }),
  );
  return result.ok ? result.data : null;
}

/** Limite de páginas do sitemap (100 produtos cada), para nunca ficar em laço. */
const SITEMAP_MAX_PAGES = 100;

/**
 * Slugs de todos os produtos ativos, paginando a API. Qualquer erro lança: o sitemap responde
 * com erro em vez de publicar uma lista truncada.
 */
export async function allProductSlugs(): Promise<string[]> {
  const slugs: string[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < SITEMAP_MAX_PAGES; page++) {
    const result = await listProducts({}, { size: [], color: [], sort: "newest" }, cursor, 100);
    if (!result.ok) throw new Error(`Catálogo ${result.reason} ao montar o sitemap`);
    slugs.push(...result.data.items.map((item) => item.slug));
    if (!result.data.next_cursor) break;
    cursor = result.data.next_cursor;
  }
  return slugs;
}

/** URL pública de um arquivo do catálogo (hero da home). */
export function mediaUrl(storageKey: string): string {
  return `${apiUrl()}/catalog/v1/media/${storageKey}`;
}
