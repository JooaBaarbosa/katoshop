import { NextRequest, NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const refreshInProxy = vi.hoisted(() => vi.fn());

vi.mock("@katoshop/api-client/session", () => ({ refreshInProxy, createSession: vi.fn() }));

const { config, proxy } = await import("../proxy");

function request(path: string, cookie?: string): NextRequest {
  return new NextRequest(`http://katoshop.localhost${path}`, {
    headers: cookie ? { cookie } : {},
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  refreshInProxy.mockImplementation((_req: NextRequest, res: NextResponse) => Promise.resolve(res));
});

describe("proxy", () => {
  it("/conta sem refresh token redireciona para o login com next", async () => {
    const response = await proxy(request("/conta"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://katoshop.localhost/entrar?next=%2Fconta");
    expect(refreshInProxy).not.toHaveBeenCalled();
  });

  it("/conta com refresh token passa pelo refresh com as opções da loja", async () => {
    const response = await proxy(request("/conta", "ks_rt=abc"));

    expect(response.headers.get("location")).toBeNull();
    expect(refreshInProxy).toHaveBeenCalledWith(
      expect.any(NextRequest),
      expect.any(NextResponse),
      expect.objectContaining({ cookiePrefix: "ks", audience: "storefront" }),
    );
  });

  it("outras páginas não exigem sessão", async () => {
    const response = await proxy(request("/entrar"));

    expect(response.headers.get("location")).toBeNull();
    expect(refreshInProxy).toHaveBeenCalledOnce();
  });

  it("o matcher ignora assets estáticos e arquivos com extensão", () => {
    const [matcher] = config.matcher;
    const re = new RegExp(`^${matcher}$`);
    expect(re.test("/conta")).toBe(true);
    expect(re.test("/")).toBe(true);
    expect(re.test("/_next/static/chunk.js")).toBe(false);
    expect(re.test("/_next/image")).toBe(false);
    expect(re.test("/favicon.ico")).toBe(false);
    expect(re.test("/icon.svg")).toBe(false);
  });
});
