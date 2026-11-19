import createClient from "openapi-fetch";
import type { paths as CartPaths } from "./generated/cart";
import type { paths as CatalogPaths } from "./generated/catalog";
import type { paths as IdentityPaths } from "./generated/identity";
import type { paths as PromotionsPaths } from "./generated/promotions";

function options(baseUrl: string, accessToken?: string) {
  return {
    baseUrl,
    ...(accessToken ? { headers: { Authorization: `Bearer ${accessToken}` } } : {}),
  };
}

export function createIdentityClient(baseUrl: string, accessToken?: string) {
  return createClient<IdentityPaths>(options(baseUrl, accessToken));
}

export function createCatalogClient(baseUrl: string, accessToken?: string) {
  return createClient<CatalogPaths>(options(baseUrl, accessToken));
}

/** Visitante: sem token, com o cabeçalho `X-Cart-Id` por chamada. Cliente: com o token. */
export function createCartClient(baseUrl: string, accessToken?: string) {
  return createClient<CartPaths>(options(baseUrl, accessToken));
}

/** Só o admin de cupons passa pelo gateway; o evaluate é da rede interna. */
export function createPromotionsClient(baseUrl: string, accessToken?: string) {
  return createClient<PromotionsPaths>(options(baseUrl, accessToken));
}
