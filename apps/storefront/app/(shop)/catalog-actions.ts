"use server";

import { fromSearchParams, parseFilters } from "../../lib/filters";
import { type ListingScope, listProducts, type ProductCardPage } from "../../lib/storefront";

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_CURSOR_LENGTH = 1024;

function slugOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" && value.length <= 120 && SLUG.test(value) ? value : undefined;
}

/**
 * Próxima página de cards de uma listagem ("Carregar mais").
 * Server action é endpoint público: escopo, filtros e cursor são revalidados aqui.
 */
export async function loadMoreProducts(
  scope: ListingScope,
  search: string,
  cursor: string,
): Promise<ProductCardPage | null> {
  if (typeof search !== "string" || typeof cursor !== "string") return null;
  if (cursor.length === 0 || cursor.length > MAX_CURSOR_LENGTH) return null;
  const category = slugOrUndefined(scope?.category);
  const collection = slugOrUndefined(scope?.collection);
  const filters = parseFilters(fromSearchParams(new URLSearchParams(search)));
  const result = await listProducts(
    { ...(category ? { category } : {}), ...(collection ? { collection } : {}) },
    filters,
    cursor,
  );
  return result.ok ? result.data : null;
}
