import { NextRequest, NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const refreshInProxy = vi.hoisted(() => vi.fn());

vi.mock("@katoshop/api-client/session", () => ({ refreshInProxy, createSession: vi.fn() }));

const { config, proxy } = await import("../proxy");

const ORIGIN = "http://admin.katoshop.localhost";

function request(path: string, cookie?: string): NextRequest {
  return new NextRequest(`${ORIGIN}${path}`, { headers: cookie ? { cookie } : {} });
}

beforeEach(() => {
  vi.clearAllMocks();
  refreshInProxy.mockImplementation((_req: NextRequest, res: NextResponse) => Promise.resolve(res));
});

describe("proxy", () => {
  it("visão geral sem refresh token vai para o login", async () => {
    const response = await proxy(request("/"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(`${ORIGIN}/entrar`);
    expect(refreshInProxy).not.toHaveBeenCalled();
  });

  it("outra página do painel sem sessão leva o destino em next", async () => {
    const response = await proxy(request("/produtos?status=draft"));

    expect(response.headers.get("location")).toBe(
      `${ORIGIN}/entrar?next=%2Fprodutos%3Fstatus%3Ddraft`,
    );
  });

  it("com refresh token passa pelo refresh com as opções do admin", async () => {
    const response = await proxy(request("/", "ka_rt=abc"));

    expect(response.headers.get("location")).toBeNull();
    expect(refreshInProxy).toHaveBeenCalledWith(
      expect.any(NextRequest),
      expect.any(NextResponse),
      expect.objectContaining({ cookiePrefix: "ka", audience: "admin" }),
    );
  });

  it("o cookie da loja não abre o painel", async () => {
    const response = await proxy(request("/", "ks_rt=abc"));

    expect(response.headers.get("location")).toBe(`${ORIGIN}/entrar`);
  });

  it.each(["/entrar", "/sair"])("%s não exige sessão", async (path) => {
    const response = await proxy(request(path));

    expect(response.headers.get("location")).toBeNull();
    expect(refreshInProxy).toHaveBeenCalledOnce();
  });

  it("o matcher ignora assets estáticos e arquivos com extensão", () => {
    const [matcher] = config.matcher;
    const re = new RegExp(`^${matcher}$`);
    expect(re.test("/")).toBe(true);
    expect(re.test("/produtos")).toBe(true);
    expect(re.test("/_next/static/chunk.js")).toBe(false);
    expect(re.test("/_next/image")).toBe(false);
    expect(re.test("/favicon.ico")).toBe(false);
    expect(re.test("/icon.svg")).toBe(false);
  });
});
