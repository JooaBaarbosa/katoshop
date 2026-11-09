import { refreshInProxy } from "@katoshop/api-client/session";
import { NextResponse, type NextRequest } from "next/server";
import { sessionOptions } from "./lib/session";

/** Páginas abertas sem sessão: o login e a rota que encerra a sessão. */
const PUBLIC_PATHS = new Set(["/entrar", "/sair"]);

/**
 * Todo o painel exige sessão. Sem `ka_rt`, vai direto ao login; com ele, este é o único ponto
 * onde a sessão é renovada (Ruling R18): aqui os cookies são graváveis.
 */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname, search } = request.nextUrl;
  if (!PUBLIC_PATHS.has(pathname) && !request.cookies.get("ka_rt")) {
    const login = new URL("/entrar", request.url);
    if (pathname !== "/") login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }
  return refreshInProxy(request, NextResponse.next(), sessionOptions());
}

export const config = {
  // páginas apenas: fora assets do Next, ícones e qualquer arquivo com extensão
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico|.*\\.[^/]+$).*)"],
};
