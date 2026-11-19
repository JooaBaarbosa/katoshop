import "server-only";
import { createCartClient, createCatalogClient, createIdentityClient } from "@katoshop/api-client";
import { apiUrl } from "./env";

export function identity(accessToken?: string) {
  return createIdentityClient(`${apiUrl()}/identity`, accessToken);
}

export function catalog(accessToken?: string) {
  return createCatalogClient(`${apiUrl()}/catalog`, accessToken);
}

/** Visitante: sem token e com `X-Cart-Id` por chamada (veja lib/cart.ts). */
export function cart(accessToken?: string) {
  return createCartClient(`${apiUrl()}/cart`, accessToken);
}

/** `fetch` com revalidação do Next, para passar por chamada: `GET(path, { fetch: revalidate(60) })`. */
export function revalidate(seconds: number) {
  return (request: Request) => fetch(request, { next: { revalidate: seconds } });
}
