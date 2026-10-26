import "server-only";
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
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
  /**
   * Chama `fn` com o access token. Por padrão (`refresh: false`) é seguro em contextos somente
   * leitura (Server Components): um 401 vira ApiProblem 401 sem renovar nem mexer em cookies.
   * Com `refresh: true` (Server Actions, Route Handlers) um 401 faz um único refresh.
   */
  withAuth<T>(fn: (token: string) => Promise<T>, options?: WithAuthOptions): Promise<T>;
  /** Renova os tokens e regrava os cookies. Só em contextos com cookies graváveis. */
  refresh(): Promise<string>;
}

export interface WithAuthOptions {
  refresh?: boolean;
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
 * Refresh em voo, compartilhado por (identityBaseUrl, refresh token). O refresh token é um
 * segredo do portador, então compartilhar a promessa entre sessões/requisições do mesmo
 * token é seguro e evita duas rotações; cada chamador grava o par nos próprios cookies.
 */
const inflight = new Map<string, Promise<TokenPair>>();

function sharedRefresh(identityBaseUrl: string, refreshToken: string): Promise<TokenPair> {
  const key = `${identityBaseUrl}|${refreshToken}`;
  let pending = inflight.get(key);
  if (!pending) {
    const client = createIdentityClient(identityBaseUrl);
    pending = client
      .POST("/v1/auth/refresh", { body: { refresh_token: refreshToken } })
      .then((result) => unwrap(result))
      .finally(() => inflight.delete(key));
    inflight.set(key, pending);
  }
  return pending;
}

/**
 * Crie uma sessão por requisição.
 *
 * Contextos: o refresh só é permitido onde cookies são graváveis. Em Server Components (somente
 * leitura) use `withAuth(fn)` (padrão `refresh: false`): um 401 lança ApiProblem 401 e o chamador
 * redireciona ao login; a renovação acontece no proxy.ts via `refreshInProxy`. Em Server Actions e
 * Route Handlers use `withAuth(fn, { refresh: true })`.
 */
export function createSession(opts: SessionOptions): Session {
  const store = opts.cookies ?? nextCookieStore;
  const accessName = `${opts.cookiePrefix}_at`;
  const refreshName = `${opts.cookiePrefix}_rt`;

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

  async function refresh(): Promise<string> {
    const refreshToken = await store.get(refreshName);
    if (!refreshToken) {
      await clear();
      throw new ApiProblem({ status: 401, code: "auth.missing_token", message: "Não autenticado" });
    }
    let pair: TokenPair;
    try {
      pair = await sharedRefresh(opts.identityBaseUrl, refreshToken);
    } catch (error) {
      // só uma recusa do identity (4xx) encerra a sessão; 5xx e falhas de rede preservam os cookies
      if (error instanceof ApiProblem && error.status >= 400 && error.status < 500) {
        await clear();
        throw new ApiProblem({
          status: 401,
          code: "auth.session_expired",
          message: "Sessão expirada",
          cause: error,
          ...(error.traceId ? { traceId: error.traceId } : {}),
        });
      }
      throw error;
    }
    await setTokens(pair);
    return pair.access_token;
  }

  async function withAuth<T>(
    fn: (token: string) => Promise<T>,
    options: WithAuthOptions = {},
  ): Promise<T> {
    const allowRefresh = options.refresh === true;
    let token = await getAccessToken();
    if (token === null) {
      if (!allowRefresh) {
        throw new ApiProblem({
          status: 401,
          code: "auth.missing_token",
          message: "Não autenticado",
        });
      }
      token = await refresh();
    }
    try {
      return await fn(token);
    } catch (error) {
      if (!allowRefresh || !(error instanceof ApiProblem) || error.status !== 401) throw error;
      // outra chamada pode já ter renovado enquanto esta estava em voo
      const current = await getAccessToken();
      const fresh = current !== null && current !== token ? current : await refresh();
      return fn(fresh);
    }
  }

  return { audience: opts.audience, getAccessToken, setTokens, clear, withAuth, refresh };
}

/**
 * Para o proxy.ts do Next (onde cookies são graváveis): se `<prefix>_at` expirou e há
 * `<prefix>_rt`, renova e grava os cookies na resposta E na requisição encaminhada, para que a
 * mesma renderização já veja o novo access token. Passe o resultado de `NextResponse.next()`.
 * Falha do identity (5xx/rede) mantém os cookies e segue sem renovar; recusa (4xx) limpa.
 */
export async function refreshInProxy(
  request: NextRequest,
  response: NextResponse,
  opts: Omit<SessionOptions, "cookies">,
): Promise<NextResponse> {
  const accessName = `${opts.cookiePrefix}_at`;
  const refreshName = `${opts.cookiePrefix}_rt`;
  if (request.cookies.get(accessName) || !request.cookies.get(refreshName)) return response;

  const pendingOut: { name: string; value: string; options: CookieOptions }[] = [];
  const adapter: CookieStore = {
    get: (name) => Promise.resolve(request.cookies.get(name)?.value),
    set: (name, value, options) => {
      request.cookies.set(name, value);
      pendingOut.push({ name, value, options });
      return Promise.resolve();
    },
    delete: (name) => {
      request.cookies.delete(name);
      pendingOut.push({
        name,
        value: "",
        options: { httpOnly: true, sameSite: "lax", path: "/", secure: opts.secure, maxAge: 0 },
      });
      return Promise.resolve();
    },
  };

  try {
    await createSession({ ...opts, cookies: adapter }).refresh();
  } catch {
    // Recusa (4xx): os cookies já foram limpos e a página redireciona ao login.
    // 5xx ou rede: nada foi gravado e a requisição segue; a próxima tentativa renova.
  }
  if (pendingOut.length === 0) return response;

  const headers = new Headers(request.headers);
  headers.set("cookie", request.cookies.toString());
  const forwarded = NextResponse.next({ request: { headers } });
  for (const [key, value] of response.headers) {
    if (!key.startsWith("x-middleware-")) forwarded.headers.set(key, value);
  }
  for (const cookie of response.cookies.getAll()) forwarded.cookies.set(cookie);
  for (const { name, value, options } of pendingOut) forwarded.cookies.set(name, value, options);
  return forwarded;
}
