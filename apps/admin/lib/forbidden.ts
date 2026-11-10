import { ApiProblem } from "@katoshop/api-client";

/** Página de leitura (Server Component) sem a permissão exigida. */
export const READ_FORBIDDEN = "Você não tem permissão para acessar esta área.";
/** Escrita (Server Action) sem a permissão exigida. */
export const WRITE_FORBIDDEN = "Você não tem permissão para esta ação.";

/**
 * Classificador único de 403, pelo código (R25), usado por leituras e escritas:
 * - `auth.insufficient_permission`: a conta é da equipe mas não tem a permissão; a sessão fica.
 * - `auth.forbidden` (token de outra audiência, R1) ou qualquer outro 403: conta sem acesso ao
 *   painel; a sessão é encerrada (lado conservador).
 */
export function forbiddenKind(error: unknown): "permission" | "audience" | null {
  if (!(error instanceof ApiProblem) || error.status !== 403) return null;
  return error.code === "auth.insufficient_permission" ? "permission" : "audience";
}
