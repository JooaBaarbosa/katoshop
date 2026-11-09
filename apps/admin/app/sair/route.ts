import { redirect } from "next/navigation";
import type { NextRequest } from "next/server";
import { endSession } from "../../lib/sign-out";

/**
 * Origens de navegação que podem encerrar a sessão: o redirect do próprio painel (same-origin)
 * e o endereço digitado ou favorito (none). Sem o cabeçalho (clientes que não são navegador,
 * como curl) também encerra: navegadores atuais sempre o enviam e uma página de terceiros não
 * consegue removê-lo. Qualquer outra origem (cross-site, same-site) só vai ao login, sem
 * deslogar, para que um link de fora não derrube a sessão (logout CSRF).
 */
const TRUSTED_FETCH_SITES = new Set(["same-origin", "none"]);

/**
 * Encerra a sessão em nome de um Server Component, que não pode gravar cookies (R18): o guarda
 * redireciona para cá quando a conta não tem acesso ao painel.
 */
export async function GET(request: NextRequest): Promise<never> {
  const site = request.headers.get("sec-fetch-site");
  if (site !== null && !TRUSTED_FETCH_SITES.has(site)) redirect("/entrar");

  await endSession();
  const reason = new URL(request.url).searchParams.get("erro");
  redirect(reason === "acesso" ? "/entrar?erro=acesso" : "/entrar");
}
