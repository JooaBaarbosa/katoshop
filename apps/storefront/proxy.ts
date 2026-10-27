import { refreshInProxy } from "@katoshop/api-client/session";
import { NextResponse, type NextRequest } from "next/server";
import { sessionOptions } from "./lib/session";

/**
 * Único ponto da loja onde a sessão é renovada (Ruling R18): aqui os cookies são graváveis,
 * e a renderização seguinte já recebe o access token novo.
 */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;
  const isAccount = pathname === "/conta" || pathname.startsWith("/conta/");
  if (isAccount && !request.cookies.get("ks_rt")) {
    const login = new URL("/entrar", request.url);
    login.searchParams.set("next", "/conta");
    return NextResponse.redirect(login);
  }
  return refreshInProxy(request, NextResponse.next(), sessionOptions());
}

export const config = {
  // páginas apenas: fora assets do Next, ícones e qualquer arquivo com extensão
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico|.*\\.[^/]+$).*)"],
};
