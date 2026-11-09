import "server-only";
import { ApiProblem, unwrap, type IdentityComponents } from "@katoshop/api-client";
import { redirect } from "next/navigation";
import { cache } from "react";
import { identity } from "./api";
import { session } from "./session";

export type Me = IdentityComponents["schemas"]["UserOut"];

/**
 * Server Components não gravam cookies (R18): quem precisa derrubar a sessão redireciona para
 * este Route Handler, que revoga, limpa os cookies e manda ao login com o aviso.
 */
const NO_ACCESS = "/sair?erro=acesso";

/**
 * Chamada autenticada somente leitura, para Server Components (a renovação é do proxy.ts).
 * 401: login. 403: o token não serve para o painel, então a sessão é encerrada.
 */
export async function authed<T>(fn: (token: string) => Promise<T>): Promise<T> {
  try {
    return await session.withAuth(fn);
  } catch (error) {
    if (error instanceof ApiProblem && error.status === 401) redirect("/entrar");
    if (error instanceof ApiProblem && error.status === 403) redirect(NO_ACCESS);
    throw error;
  }
}

/** Funcionário logado ou redirect. Memoizado por requisição: layout e página dividem a chamada. */
export const requireStaff = cache(async (): Promise<Me> => {
  const me = await authed(async (token) => unwrap(await identity(token).GET("/v1/me")));
  if (me.kind !== "staff") redirect(NO_ACCESS);
  return me;
});
