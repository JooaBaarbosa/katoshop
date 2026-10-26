export { ApiProblem, unwrap, type ApiProblemInit } from "./errors";
export { createCatalogClient, createIdentityClient } from "./clients";
export type { components as CatalogComponents, paths as CatalogPaths } from "./generated/catalog";
export type {
  components as IdentityComponents,
  paths as IdentityPaths,
} from "./generated/identity";
// A sessão BFF (server-only) fica em "@katoshop/api-client/session".
