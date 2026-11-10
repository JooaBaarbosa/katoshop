import "server-only";
import { ApiProblem, unwrap, type CatalogComponents } from "@katoshop/api-client";
import { notFound } from "next/navigation";
import { catalog } from "./api";
import { authed } from "./guard";

type Schemas = CatalogComponents["schemas"];
export type AdminProduct = Schemas["AdminProduct"];
export type AdminProductRow = Schemas["AdminProductRow"];
export type AdminVariant = Schemas["AdminVariantWithPrice"];
export type AdminImage = Schemas["AdminImage"];
export type Category = Schemas["CategoryOut"];
export type Collection = Schemas["CollectionOut"];
export type Movement = Schemas["MovementOut"];
export type ProductStatus = AdminProductRow["status"];

/** Leituras do painel (Server Components): 404 do recurso vira a página "não encontrado". */
async function orNotFound<T>(load: () => Promise<T>): Promise<T> {
  try {
    return await load();
  } catch (error) {
    if (error instanceof ApiProblem && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
}

export function getProduct(id: string): Promise<AdminProduct> {
  return orNotFound(() =>
    authed(async (token) =>
      unwrap(
        await catalog(token).GET("/v1/admin/products/{product_id}", {
          params: { path: { product_id: id } },
        }),
      ),
    ),
  );
}

export async function listCategories(): Promise<Category[]> {
  const page = await authed(async (token) =>
    unwrap(await catalog(token).GET("/v1/admin/categories")),
  );
  return page.items;
}

export async function listCollections(): Promise<Collection[]> {
  const page = await authed(async (token) =>
    unwrap(await catalog(token).GET("/v1/admin/collections")),
  );
  return page.items;
}

export async function getCollection(id: string): Promise<Collection> {
  const found = (await listCollections()).find((collection) => collection.id === id);
  if (!found) notFound();
  return found;
}

export type ProductQuery = {
  q?: string;
  status?: ProductStatus;
  category?: string;
  cursor?: string;
};

export function listProducts(query: ProductQuery, limit = 24) {
  return authed(async (token) =>
    unwrap(
      await catalog(token).GET("/v1/admin/products", {
        params: { query: { ...query, limit } },
      }),
    ),
  );
}

/** Todos os produtos (para o seletor das coleções). Escala de demo: poucas páginas de 100. */
export async function listAllProducts(): Promise<AdminProductRow[]> {
  const items: AdminProductRow[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < 20; page += 1) {
    const result = await listProducts(cursor ? { cursor } : {}, 100);
    items.push(...result.items);
    if (!result.next_cursor) return items;
    cursor = result.next_cursor;
  }
  throw new Error("Lista de produtos maior que o esperado para o seletor de coleções.");
}

export function listMovements(variantId: string, cursor?: string) {
  return authed(async (token) =>
    unwrap(
      await catalog(token).GET("/v1/admin/variants/{variant_id}/stock-movements", {
        params: { path: { variant_id: variantId }, query: { ...(cursor ? { cursor } : {}) } },
      }),
    ),
  );
}
