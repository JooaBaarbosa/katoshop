import "server-only";
import { createSession, type SessionOptions } from "@katoshop/api-client/session";
import { cookies } from "next/headers";
import { apiUrl } from "./env";

/** Opções da sessão da loja; o proxy.ts usa as mesmas no refreshInProxy. */
export function sessionOptions(): Omit<SessionOptions, "cookies"> {
  return {
    cookiePrefix: "ks",
    audience: "storefront",
    identityBaseUrl: `${apiUrl()}/identity`,
    // em http local o cookie não pode ser Secure; em produção COOKIE_SECURE=true
    secure: process.env.COOKIE_SECURE === "true",
  };
}

/**
 * Sessão BFF da loja. Os cookies são lidos por chamada (next/headers), então um objeto por
 * módulo atende todas as requisições. Server Components: `withAuth(fn)`; Server Actions:
 * `withAuth(fn, { refresh: true })`.
 */
export const session = createSession(sessionOptions());

/** Refresh token atual, para revogar no logout. */
export async function getRefreshToken(): Promise<string | undefined> {
  return (await cookies()).get("ks_rt")?.value;
}
