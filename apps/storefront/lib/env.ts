/** Base do gateway. No compose: http://api.katoshop.localhost (alias do Traefik na rede). */
export function apiUrl(): string {
  return process.env.API_URL ?? "http://api.katoshop.localhost";
}

/**
 * Base do cart para o BFF (S13). No compose: http://cart:8000, pela rede interna, sem passar
 * pelo gateway: o limite por IP do router público /cart não junta todos os clientes no IP do
 * container da loja (R20). Sem a variável, usa o gateway (`API_URL/cart`).
 */
export function cartApiUrl(): string {
  const internal = process.env.CART_API_URL?.replace(/\/+$/, "");
  return internal || `${apiUrl()}/cart`;
}

/** Endereço público da loja, para URLs absolutas (sitemap, robots, Open Graph, JSON-LD). */
export function siteUrl(): string {
  return (process.env.SITE_URL ?? "http://katoshop.localhost").replace(/\/+$/, "");
}
