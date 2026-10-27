import "server-only";
import { createCatalogClient, createIdentityClient } from "@katoshop/api-client";
import { apiUrl } from "./env";

export function identity(accessToken?: string) {
  return createIdentityClient(`${apiUrl()}/identity`, accessToken);
}

export function catalog(accessToken?: string) {
  return createCatalogClient(`${apiUrl()}/catalog`, accessToken);
}

/** `fetch` com revalidação do Next, para passar por chamada: `GET(path, { fetch: revalidate(60) })`. */
export function revalidate(seconds: number) {
  return (request: Request) => fetch(request, { next: { revalidate: seconds } });
}
