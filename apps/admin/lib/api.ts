import "server-only";
import { createCatalogClient, createIdentityClient } from "@katoshop/api-client";
import { apiUrl } from "./env";

export function identity(accessToken?: string) {
  return createIdentityClient(`${apiUrl()}/identity`, accessToken);
}

export function catalog(accessToken?: string) {
  return createCatalogClient(`${apiUrl()}/catalog`, accessToken);
}
