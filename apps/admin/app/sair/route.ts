import { redirect } from "next/navigation";
import type { NextRequest } from "next/server";
import { endSession } from "../../lib/sign-out";

/**
 * Encerra a sessão em nome de um Server Component, que não pode gravar cookies (R18): o guarda
 * redireciona para cá quando a conta não tem acesso ao painel.
 */
export async function GET(request: NextRequest): Promise<never> {
  await endSession();
  const reason = new URL(request.url).searchParams.get("erro");
  redirect(reason === "acesso" ? "/entrar?erro=acesso" : "/entrar");
}
