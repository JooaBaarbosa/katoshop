import "server-only";
import { createSession, type SessionOptions } from "@katoshop/api-client/session";
import { cookies } from "next/headers";
import { apiUrl } from "./env";

/** Opções da sessão do admin; o proxy.ts usa as mesmas no refreshInProxy. */
export function sessionOptions(): Omit<SessionOptions, "cookies"> {
  return {
    cookiePrefix: "ka",
    audience: "admin",
    identityBaseUrl: `${apiUrl()}/identity`,
    // em http local o cookie não pode ser Secure; em produção COOKIE_SECURE=true
    secure: process.env.COOKIE_SECURE === "true",
  };
}

/**
 * Sessão BFF do admin (cookies ka_at e ka_rt, audiência admin). Server Components:
 * `withAuth(fn)`; Server Actions e Route Handlers: `withAuth(fn, { refresh: true })` (R18).
 */
export const session = createSession(sessionOptions());

/** Refresh token atual, para revogar no logout. */
export async function getRefreshToken(): Promise<string | undefined> {
  return (await cookies()).get("ka_rt")?.value;
}
