/** Base do gateway. No compose: http://api.katoshop.localhost (alias do Traefik na rede). */
export function apiUrl(): string {
  return process.env.API_URL ?? "http://api.katoshop.localhost";
}

/** Endereço público da loja, para URLs absolutas (sitemap, robots, Open Graph, JSON-LD). */
export function siteUrl(): string {
  return (process.env.SITE_URL ?? "http://katoshop.localhost").replace(/\/+$/, "");
}
