import "server-only";
import { ApiProblem, unwrap } from "@katoshop/api-client";
import { redirect } from "next/navigation";
import { identity } from "./api";
import { problemMessage } from "./problem-messages";
import { session } from "./session";

export const PERMISSION_DENIED = "Você não tem permissão para esta ação.";
const NO_ACCESS = "/sair?erro=acesso";

export type Failure = {
  ok: false;
  error: string;
  code?: string;
  fieldErrors?: Record<string, string>;
};
export type Outcome<T> = { ok: true; data: T } | Failure;

class NotStaff extends Error {}

/**
 * O catálogo usa o mesmo código `auth.forbidden` para audiência errada e para permissão
 * insuficiente (R1); só o detalhe os separa. Só a falta de permissão mantém a sessão: qualquer
 * outro 403 continua encerrando, como no guarda das páginas.
 */
function isPermissionDenied(error: ApiProblem): boolean {
  return error.code === "auth.forbidden" && error.message === "Permissão insuficiente.";
}

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
 * sessão; falta de permissão numa escrita só mostra o aviso.
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
    if (error instanceof NotStaff) redirect(NO_ACCESS);
    if (error instanceof ApiProblem) {
      if (error.status === 401) redirect("/entrar");
      if (error.status === 403) {
        if (isPermissionDenied(error)) {
          return { ok: false, code: error.code, error: PERMISSION_DENIED };
        }
        redirect(NO_ACCESS);
      }
      const fieldErrors = fieldErrorsOf(error);
      return {
        ok: false,
        code: error.code,
        error: problemMessage(error),
        ...(fieldErrors ? { fieldErrors } : {}),
      };
    }
    return { ok: false, error: problemMessage(error) };
  }
}
