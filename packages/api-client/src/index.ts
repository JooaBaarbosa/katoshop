export { ApiProblem, unwrap, type ApiProblemInit } from "./errors";
export {
  createCartClient,
  createCatalogClient,
  createIdentityClient,
  createPromotionsClient,
} from "./clients";
export type { components as CartComponents, paths as CartPaths } from "./generated/cart";
export type { components as CatalogComponents, paths as CatalogPaths } from "./generated/catalog";
export type {
  components as IdentityComponents,
  paths as IdentityPaths,
} from "./generated/identity";
export type {
  components as PromotionsComponents,
  paths as PromotionsPaths,
} from "./generated/promotions";
// A sessão BFF (server-only) fica em "@katoshop/api-client/session".
