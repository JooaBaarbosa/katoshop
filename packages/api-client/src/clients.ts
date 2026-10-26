import createClient from "openapi-fetch";
import type { paths as CatalogPaths } from "./generated/catalog";
import type { paths as IdentityPaths } from "./generated/identity";

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
