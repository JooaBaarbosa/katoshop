import "server-only";
import { ApiProblem, unwrap } from "@katoshop/api-client";
import { redirect, unstable_rethrow } from "next/navigation";
import { identity } from "./api";
import { forbiddenKind, WRITE_FORBIDDEN } from "./forbidden";
import { problemMessage } from "./problem-messages";
import { session } from "./session";

export const PERMISSION_DENIED = WRITE_FORBIDDEN;
const NO_ACCESS = "/sair?erro=acesso";

export type Failure = {
  ok: false;
  error: string;
  code?: string;
  fieldErrors?: Record<string, string>;
};
export type Outcome<T> = { ok: true; data: T } | Failure;

class NotStaff extends Error {}

function fieldErrorsOf(error: ApiProblem): Record<string, string> | undefined {
  if (!error.errors) return undefined;
  const entries = Object.entries(error.errors).filter(([, items]) => items.length > 0);
  if (entries.length === 0) return undefined;
  return Object.fromEntries(entries.map(([field, items]) => [field, items[0] ?? ""]));
}

/**
 * Toda Server Action do painel passa por aqui: confere de novo que a sessão é de funcionário
 * (a action é um endpoint POST público, não herda o guarda da página) com refresh habilitado
 * (R18) e converte falhas da API em mensagens. 401 vai ao login; conta sem acesso encerra a
 * sessão; falta de permissão numa escrita só mostra o aviso. redirect()/notFound() lançados
 * dentro de `fn` sobem intactos para o Next.
 */
export async function staffAction<T>(fn: (token: string) => Promise<T>): Promise<Outcome<T>> {
  try {
    const data = await session.withAuth(
      async (token) => {
        const me = unwrap(await identity(token).GET("/v1/me"));
        if (me.kind !== "staff") throw new NotStaff();
        return fn(token);
      },
      { refresh: true },
    );
    return { ok: true, data };
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof NotStaff) redirect(NO_ACCESS);
    if (error instanceof ApiProblem) {
      if (error.status === 401) redirect("/entrar");
      const forbidden = forbiddenKind(error);
      if (forbidden === "permission") {
        return { ok: false, code: error.code, error: PERMISSION_DENIED };
      }
      if (forbidden === "audience") redirect(NO_ACCESS);
      if (error.status >= 500) {
        console.error(`[staffAction] ${error.code} trace_id=${error.traceId ?? "-"}`, error);
      }
      const fieldErrors = fieldErrorsOf(error);
      return {
        ok: false,
        code: error.code,
        error: problemMessage(error),
        ...(fieldErrors ? { fieldErrors } : {}),
      };
    }
    console.error("[staffAction] falha inesperada", error);
    return { ok: false, error: problemMessage(error) };
  }
}
