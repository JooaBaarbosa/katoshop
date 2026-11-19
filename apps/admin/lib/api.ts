import "server-only";
import {
  createCatalogClient,
  createIdentityClient,
  createPromotionsClient,
} from "@katoshop/api-client";
import { apiUrl } from "./env";

export function identity(accessToken?: string) {
  return createIdentityClient(`${apiUrl()}/identity`, accessToken);
}

export function catalog(accessToken?: string) {
  return createCatalogClient(`${apiUrl()}/catalog`, accessToken);
}

/** Só o admin de cupons (`/promotions/v1/admin/*`) passa pelo gateway. */
export function promotions(accessToken?: string) {
  return createPromotionsClient(`${apiUrl()}/promotions`, accessToken);
}
