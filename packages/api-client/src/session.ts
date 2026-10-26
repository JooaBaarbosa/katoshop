import "server-only";
import { cookies } from "next/headers";
import { createIdentityClient } from "./clients";
import { ApiProblem, unwrap } from "./errors";
import type { components } from "./generated/identity";

export type TokenPair = components["schemas"]["TokenPairOut"];

export interface CookieOptions {
  httpOnly: boolean;
  sameSite: "lax";
  path: string;
  secure: boolean;
  maxAge?: number;
  expires?: Date;
}

/** Acesso a cookies injetável: o padrão usa next/headers; os testes usam um falso. */
export interface CookieStore {
  get(name: string): Promise<string | undefined>;
  set(name: string, value: string, options: CookieOptions): Promise<void>;
  delete(name: string): Promise<void>;
}

export interface SessionOptions {
  cookiePrefix: "ks" | "ka";
  audience: "storefront" | "admin";
  identityBaseUrl: string;
  secure: boolean;
  cookies?: CookieStore;
}

export interface Session {
  readonly audience: "storefront" | "admin";
  getAccessToken(): Promise<string | null>;
  setTokens(pair: TokenPair): Promise<void>;
  clear(): Promise<void>;
  withAuth<T>(fn: (token: string) => Promise<T>): Promise<T>;
}

const ACCESS_MAX_AGE_SECONDS = 900;

export const nextCookieStore: CookieStore = {
  async get(name) {
    return (await cookies()).get(name)?.value;
  },
  async set(name, value, options) {
    (await cookies()).set(name, value, options);
  },
  async delete(name) {
    (await cookies()).delete(name);
  },
};

/**
 * Crie uma sessão por requisição. O refresh em voo é compartilhado por refresh token, então
 * chamadas concorrentes de withAuth nunca renovam duas vezes o mesmo token.
 */
export function createSession(opts: SessionOptions): Session {
  const store = opts.cookies ?? nextCookieStore;
  const accessName = `${opts.cookiePrefix}_at`;
  const refreshName = `${opts.cookiePrefix}_rt`;
  const inflight = new Map<string, Promise<string>>();

  const base = {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure: opts.secure,
  } as const;

  async function getAccessToken(): Promise<string | null> {
    return (await store.get(accessName)) ?? null;
  }

  async function setTokens(pair: TokenPair): Promise<void> {
    await store.set(accessName, pair.access_token, { ...base, maxAge: ACCESS_MAX_AGE_SECONDS });
    await store.set(refreshName, pair.refresh_token, {
      ...base,
      expires: new Date(pair.refresh_expires_at),
    });
  }

  async function clear(): Promise<void> {
    await store.delete(accessName);
    await store.delete(refreshName);
  }

  async function doRefresh(refreshToken: string): Promise<string> {
    try {
      const client = createIdentityClient(opts.identityBaseUrl);
      const pair = unwrap(
        await client.POST("/v1/auth/refresh", { body: { refresh_token: refreshToken } }),
      );
      await setTokens(pair);
      return pair.access_token;
    } catch (error) {
      await clear();
      throw new ApiProblem({
        status: 401,
        code: "auth.session_expired",
        message: "Sessão expirada",
        ...(error instanceof ApiProblem && error.traceId ? { traceId: error.traceId } : {}),
      });
    }
  }

  /** Renova uma vez por refresh token; chamadas simultâneas aguardam a mesma promessa. */
  async function refresh(): Promise<string> {
    const refreshToken = await store.get(refreshName);
    if (!refreshToken) {
      await clear();
      throw new ApiProblem({
        status: 401,
        code: "auth.missing_token",
        message: "Não autenticado",
      });
    }
    let pending = inflight.get(refreshToken);
    if (!pending) {
      pending = doRefresh(refreshToken).finally(() => inflight.delete(refreshToken));
      inflight.set(refreshToken, pending);
    }
    return pending;
  }

  async function withAuth<T>(fn: (token: string) => Promise<T>): Promise<T> {
    const token = (await getAccessToken()) ?? (await refresh());
    try {
      return await fn(token);
    } catch (error) {
      if (!(error instanceof ApiProblem) || error.status !== 401) throw error;
      // outra chamada pode já ter renovado enquanto esta estava em voo
      const current = await getAccessToken();
      const fresh = current !== null && current !== token ? current : await refresh();
      return fn(fresh);
    }
  }

  return { audience: opts.audience, getAccessToken, setTokens, clear, withAuth };
}
