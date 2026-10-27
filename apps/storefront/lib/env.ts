/** Base do gateway. No compose: http://api.katoshop.localhost (alias do Traefik na rede). */
export function apiUrl(): string {
  return process.env.API_URL ?? "http://api.katoshop.localhost";
}
