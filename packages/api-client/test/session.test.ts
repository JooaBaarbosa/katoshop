import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { ApiProblem } from "../src/errors";
import { createSession, type CookieOptions, type CookieStore } from "../src/session";

class FakeCookieStore implements CookieStore {
  values = new Map<string, string>();
  setCalls: { name: string; value: string; options: CookieOptions }[] = [];
  deleted: string[] = [];

  get(name: string): Promise<string | undefined> {
    return Promise.resolve(this.values.get(name));
  }
  set(name: string, value: string, options: CookieOptions): Promise<void> {
    this.values.set(name, value);
    this.setCalls.push({ name, value, options });
    return Promise.resolve();
  }
  delete(name: string): Promise<void> {
    this.values.delete(name);
    this.deleted.push(name);
    return Promise.resolve();
  }
}

const REFRESH_EXPIRES = "2026-11-25T12:00:00Z";

function pair(suffix: string) {
  return {
    access_token: `at-${suffix}`,
    refresh_token: `rt-${suffix}`,
    expires_in: 900,
    refresh_expires_at: REFRESH_EXPIRES,
    user: { id: "u1", email: "a@b.c", name: "A", kind: "customer", roles: [] },
  };
}

function unauthorized(): ApiProblem {
  return new ApiProblem({ status: 401, code: "auth.invalid_token", message: "expired" });
}

type Fn = (token: string) => Promise<string>;

let store: FakeCookieStore;
let fetchMock: Mock<(...args: unknown[]) => Promise<Response>>;

function makeSession(prefix: "ks" | "ka" = "ks") {
  return createSession({
    cookiePrefix: prefix,
    audience: prefix === "ks" ? "storefront" : "admin",
    identityBaseUrl: "http://api.test/identity",
    secure: true,
    cookies: store,
  });
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status < 400 ? "application/json" : "application/problem+json" },
  });
}

beforeEach(() => {
  store = new FakeCookieStore();
  fetchMock = vi.fn<(...args: unknown[]) => Promise<Response>>();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("setTokens / getAccessToken / clear", () => {
  it("grava os cookies <prefix>_at e <prefix>_rt com as opções exigidas", async () => {
    const session = makeSession("ka");
    await session.setTokens(pair("1"));

    const at = store.setCalls.find((c) => c.name === "ka_at");
    const rt = store.setCalls.find((c) => c.name === "ka_rt");
    expect(at?.value).toBe("at-1");
    expect(at?.options).toEqual({
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure: true,
      maxAge: 900,
    });
    expect(rt?.value).toBe("rt-1");
    expect(rt?.options).toEqual({
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure: true,
      expires: new Date(REFRESH_EXPIRES),
    });
    expect(await session.getAccessToken()).toBe("at-1");
  });

  it("getAccessToken devolve null sem cookie", async () => {
    expect(await makeSession().getAccessToken()).toBeNull();
  });

  it("clear apaga os dois cookies", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    await session.clear();
    expect(store.deleted.sort()).toEqual(["ks_at", "ks_rt"]);
    expect(await session.getAccessToken()).toBeNull();
  });
});

describe("withAuth", () => {
  it("repassa o token e o resultado quando não há erro", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    const fn = vi.fn((token: string) => Promise.resolve(`ok:${token}`));

    expect(await session.withAuth(fn)).toBe("ok:at-1");
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("em 401 faz um refresh, regrava os cookies e repete com o token novo", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    fetchMock.mockResolvedValueOnce(jsonResponse(200, pair("2")));
    const fn = vi.fn<Fn>().mockRejectedValueOnce(unauthorized()).mockResolvedValueOnce("depois");

    expect(await session.withAuth(fn)).toBe("depois");

    expect(fn.mock.calls.map((c) => c[0])).toEqual(["at-1", "at-2"]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.url).toBe("http://api.test/identity/v1/auth/refresh");
    expect(request.method).toBe("POST");
    expect(await request.json()).toEqual({ refresh_token: "rt-1" });
    expect(store.values.get("ks_at")).toBe("at-2");
    expect(store.values.get("ks_rt")).toBe("rt-2");
  });

  it("repete só uma vez: segundo 401 após o refresh é propagado", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    fetchMock.mockResolvedValueOnce(jsonResponse(200, pair("2")));
    const fn = vi.fn<Fn>().mockRejectedValue(unauthorized());

    await expect(session.withAuth(fn)).rejects.toMatchObject({ status: 401 });
    expect(fn).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("não tenta refresh para erros que não são 401", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    const forbidden = new ApiProblem({ status: 403, code: "auth.forbidden", message: "no" });
    const fn = vi.fn<Fn>().mockRejectedValue(forbidden);

    await expect(session.withAuth(fn)).rejects.toBe(forbidden);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refresh falhando limpa os cookies e lança ApiProblem 401", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, {
        type: "about:blank",
        title: "Unauthorized",
        status: 401,
        detail: "revoked",
        code: "identity.auth.invalid_refresh_token",
        trace_id: "t",
      }),
    );
    const fn = vi.fn<Fn>().mockRejectedValue(unauthorized());

    const failure = await session.withAuth(fn).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiProblem);
    expect((failure as ApiProblem).status).toBe(401);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(store.values.has("ks_at")).toBe(false);
    expect(store.values.has("ks_rt")).toBe(false);
  });

  it("falha de rede no refresh também limpa os cookies e vira 401", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"));
    const fn = vi.fn<Fn>().mockRejectedValue(unauthorized());

    await expect(session.withAuth(fn)).rejects.toMatchObject({ status: 401 });
    expect(store.values.size).toBe(0);
  });

  it("sem access token mas com refresh token, renova antes de chamar fn", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    store.values.delete("ks_at");
    fetchMock.mockResolvedValueOnce(jsonResponse(200, pair("2")));
    const fn = vi.fn((token: string) => Promise.resolve(token));

    expect(await session.withAuth(fn)).toBe("at-2");
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("sem nenhum cookie lança 401 sem chamar fn nem a rede", async () => {
    const session = makeSession();
    const fn = vi.fn((token: string) => Promise.resolve(token));

    await expect(session.withAuth(fn)).rejects.toMatchObject({
      status: 401,
      code: "auth.missing_token",
    });
    expect(fn).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("chamadas concorrentes na mesma sessão fazem um único refresh", async () => {
    const session = makeSession();
    await session.setTokens(pair("1"));
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    fetchMock.mockImplementation(() => gate.then(() => jsonResponse(200, pair("2"))));
    const makeFn = () =>
      vi.fn((token: string) =>
        token === "at-1" ? Promise.reject(unauthorized()) : Promise.resolve(token),
      );
    const fnA = makeFn();
    const fnB = makeFn();

    const pending = Promise.all([session.withAuth(fnA), session.withAuth(fnB)]);
    // deixa as duas chamadas baterem no 401 antes de liberar o refresh
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    await new Promise<void>((resolve) => {
      setTimeout(resolve, 10);
    });
    release();

    expect(await pending).toEqual(["at-2", "at-2"]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fnA).toHaveBeenCalledTimes(2);
    expect(fnB).toHaveBeenCalledTimes(2);
  });

  it("um 401 tardio, depois de outra chamada já ter renovado, reaproveita o token novo", async () => {
    const session = makeSession();
    store.values.set("ks_at", "at-1");
    store.values.set("ks_rt", "rt-1");
    const fn = vi.fn<Fn>().mockImplementation((token) => {
      if (token === "at-1") {
        // outra chamada renova enquanto esta ainda estava em voo
        store.values.set("ks_at", "at-2");
        store.values.set("ks_rt", "rt-2");
        return Promise.reject(unauthorized());
      }
      return Promise.resolve(token);
    });

    expect(await session.withAuth(fn)).toBe("at-2");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
