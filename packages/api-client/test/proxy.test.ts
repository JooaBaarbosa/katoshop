import { NextRequest, NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { refreshInProxy } from "../src/session";

const opts = {
  cookiePrefix: "ks",
  audience: "storefront",
  identityBaseUrl: "http://api.test/identity",
  secure: true,
} as const;

const newPair = {
  access_token: "at-2",
  refresh_token: "rt-2",
  expires_in: 900,
  refresh_expires_at: "2026-11-25T12:00:00Z",
  user: { id: "u1", email: "a@b.c", name: "A", kind: "customer", roles: [] },
};

let fetchMock: Mock<(...args: unknown[]) => Promise<Response>>;

function requestWith(cookie: string): NextRequest {
  return new NextRequest("http://katoshop.localhost/conta", { headers: { cookie } });
}

beforeEach(() => {
  fetchMock = vi.fn<(...args: unknown[]) => Promise<Response>>();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("refreshInProxy", () => {
  it("sem at e com rt: renova, grava na resposta e encaminha o cookie novo na requisição", async () => {
    fetchMock.mockResolvedValueOnce(Response.json(newPair));
    const request = requestWith("ks_rt=rt-1; outro=x");

    const result = await refreshInProxy(request, NextResponse.next(), opts);

    expect(result.cookies.get("ks_at")?.value).toBe("at-2");
    expect(result.cookies.get("ks_rt")?.value).toBe("rt-2");
    expect(result.cookies.get("ks_at")).toMatchObject({ httpOnly: true, maxAge: 900 });
    const forwarded = result.headers.get("x-middleware-request-cookie");
    expect(forwarded).toContain("ks_at=at-2");
    expect(forwarded).toContain("ks_rt=rt-2");
    expect(forwarded).toContain("outro=x");
  });

  it("com at presente não faz nada", async () => {
    const response = NextResponse.next();
    const result = await refreshInProxy(requestWith("ks_at=at-1; ks_rt=rt-1"), response, opts);
    expect(result).toBe(response);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sem rt não faz nada", async () => {
    const response = NextResponse.next();
    expect(await refreshInProxy(requestWith("x=1"), response, opts)).toBe(response);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refresh recusado limpa os cookies na resposta", async () => {
    fetchMock.mockResolvedValueOnce(
      Response.json({ status: 401, code: "identity.auth.invalid_refresh_token" }, { status: 401 }),
    );

    const result = await refreshInProxy(requestWith("ks_rt=rt-1"), NextResponse.next(), opts);

    expect(result.cookies.get("ks_rt")?.value).toBe("");
    expect(result.cookies.get("ks_at")?.value).toBe("");
  });

  it("5xx do identity mantém os cookies e segue sem renovar", async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ status: 503 }, { status: 503 }));
    const response = NextResponse.next();

    const result = await refreshInProxy(requestWith("ks_rt=rt-1"), response, opts);

    expect(result).toBe(response);
    expect(result.cookies.getAll()).toEqual([]);
  });

  it("identity sem resposta: desiste em 2 s, mantém os cookies e segue sem renovar", async () => {
    vi.useFakeTimers();
    try {
      fetchMock.mockImplementationOnce((...args: unknown[]) => {
        const { signal } = args[0] as Request;
        return new Promise((_, reject) => {
          signal.addEventListener("abort", () => reject(signal.reason as Error));
        });
      });
      const response = NextResponse.next();

      const pending = refreshInProxy(requestWith("ks_rt=rt-1"), response, opts);
      await vi.advanceTimersByTimeAsync(2000);
      const result = await pending;

      expect(result).toBe(response);
      expect(result.cookies.getAll()).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });
});
