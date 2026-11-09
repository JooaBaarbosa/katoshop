import { beforeEach, describe, expect, it, vi } from "vitest";

// redirect() do Next lança para interromper a action; o falso faz o mesmo e guarda o destino.
class RedirectSignal extends Error {
  constructor(readonly url: string) {
    super(`redirect:${url}`);
  }
}

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  identity: vi.fn(),
  setTokens: vi.fn(),
  clear: vi.fn(),
  getRefreshToken: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new RedirectSignal(url);
  },
}));

vi.mock("../lib/api", () => ({ identity: mocks.identity }));

vi.mock("../lib/session", () => ({
  session: { setTokens: mocks.setTokens, clear: mocks.clear },
  getRefreshToken: mocks.getRefreshToken,
}));

const { loginAction } = await import("../app/entrar/actions");
const { logoutAction } = await import("../app/(painel)/actions");
const { GET: signOutRoute } = await import("../app/sair/route");

const PAIR = {
  access_token: "at",
  refresh_token: "rt",
  expires_in: 900,
  refresh_expires_at: "2026-11-26T00:00:00Z",
  user: {
    id: "u1",
    email: "admin@katoshop.localhost",
    name: "Admin",
    kind: "staff",
    roles: ["admin"],
  },
};

function ok<T>(data: T, status = 200) {
  return { data, error: undefined, response: new Response(null, { status }) };
}

function problem(status: number, body: Record<string, unknown>) {
  return { data: undefined, error: body, response: new Response(null, { status }) };
}

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

async function redirectOf(action: Promise<unknown>): Promise<string> {
  const error = await action.then(
    () => null,
    (e: unknown) => e,
  );
  if (!(error instanceof RedirectSignal)) throw new Error(`esperava redirect, veio ${String(error)}`);
  return error.url;
}

const CREDENTIALS = { email: "admin@katoshop.localhost", password: "katoshop-demo-2026" };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.identity.mockReturnValue({ POST: mocks.post });
});

describe("loginAction", () => {
  it("usa o login de funcionário, grava os tokens e vai para a visão geral", async () => {
    mocks.post.mockResolvedValue(ok(PAIR));

    const url = await redirectOf(loginAction(null, form(CREDENTIALS)));

    expect(mocks.post).toHaveBeenCalledWith("/v1/auth/staff/login", { body: CREDENTIALS });
    expect(mocks.setTokens).toHaveBeenCalledWith(PAIR);
    expect(url).toBe("/");
  });

  it("credencial de cliente (recusada pelo identity) vira mensagem genérica", async () => {
    mocks.post.mockResolvedValue(
      problem(401, { code: "identity.auth.invalid_credentials", title: "Credenciais inválidas" }),
    );

    const state = await loginAction(null, form({ email: "ana@exemplo.com", password: "x" }));

    expect(state).toMatchObject({
      ok: false,
      formError: "Email ou senha incorretos.",
      values: { email: "ana@exemplo.com" },
    });
    expect(mocks.setTokens).not.toHaveBeenCalled();
  });

  it("par de tokens que não é de funcionário nunca vira sessão", async () => {
    mocks.post.mockResolvedValue(ok({ ...PAIR, user: { ...PAIR.user, kind: "customer" } }));

    const state = await loginAction(null, form(CREDENTIALS));

    expect(state).toMatchObject({ ok: false, formError: "Email ou senha incorretos." });
    expect(mocks.setTokens).not.toHaveBeenCalled();
  });

  it("respeita next interno", async () => {
    mocks.post.mockResolvedValue(ok(PAIR));

    const url = await redirectOf(loginAction(null, form({ ...CREDENTIALS, next: "/produtos" })));

    expect(url).toBe("/produtos");
  });

  it.each(["//evil.example", "https://evil.example", "/\\evil.example", "produtos", "/ x"])(
    "ignora next externo ou malformado (%s)",
    async (next) => {
      mocks.post.mockResolvedValue(ok(PAIR));

      const url = await redirectOf(loginAction(null, form({ ...CREDENTIALS, next })));

      expect(url).toBe("/");
    },
  );

  it("campos vazios não chamam a API", async () => {
    const state = await loginAction(null, form({ email: " ", password: "" }));

    expect(state).toMatchObject({
      fieldErrors: { email: "Informe seu email.", password: "Informe sua senha." },
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("limite de tentativas (429) tem mensagem própria", async () => {
    mocks.post.mockResolvedValue(problem(429, {}));

    const state = await loginAction(null, form(CREDENTIALS));

    expect(state).toMatchObject({
      formError: "Muitas tentativas. Aguarde um instante e tente de novo.",
    });
  });

  it("falha de rede vira mensagem genérica", async () => {
    mocks.post.mockRejectedValue(new TypeError("fetch failed"));

    const state = await loginAction(null, form(CREDENTIALS));

    expect(state).toMatchObject({
      formError: "Não foi possível concluir agora. Tente de novo em instantes.",
    });
  });
});

describe("logoutAction", () => {
  it("revoga o refresh token, limpa a sessão e volta para o login", async () => {
    mocks.getRefreshToken.mockResolvedValue("rt");
    mocks.post.mockResolvedValue(ok(undefined, 204));

    const url = await redirectOf(logoutAction());

    expect(mocks.post).toHaveBeenCalledWith("/v1/auth/logout", { body: { refresh_token: "rt" } });
    expect(mocks.clear).toHaveBeenCalled();
    expect(url).toBe("/entrar");
  });

  it("limpa a sessão mesmo se o identity falhar", async () => {
    mocks.getRefreshToken.mockResolvedValue("rt");
    mocks.post.mockRejectedValue(new TypeError("fetch failed"));

    expect(await redirectOf(logoutAction())).toBe("/entrar");
    expect(mocks.clear).toHaveBeenCalled();
  });
});

describe("GET /sair (Route Handler: cookies graváveis, R18)", () => {
  function get(query = "", headers: Record<string, string> = {}) {
    return signOutRoute(
      new Request(`http://admin.katoshop.localhost/sair${query}`, { headers }) as Parameters<
        typeof signOutRoute
      >[0],
    );
  }

  it.each(["same-origin", "none"])(
    "navegação %s (redirect do próprio painel ou URL digitada) encerra a sessão",
    async (site) => {
      mocks.getRefreshToken.mockResolvedValue("rt");
      mocks.post.mockResolvedValue(ok(undefined, 204));

      const url = await redirectOf(get("?erro=acesso", { "sec-fetch-site": site }));

      expect(mocks.clear).toHaveBeenCalled();
      expect(url).toBe("/entrar?erro=acesso");
    },
  );

  it.each(["cross-site", "same-site"])(
    "navegação %s só redireciona, sem deslogar (logout CSRF)",
    async (site) => {
      mocks.getRefreshToken.mockResolvedValue("rt");

      const url = await redirectOf(get("?erro=acesso", { "sec-fetch-site": site }));

      expect(mocks.post).not.toHaveBeenCalled();
      expect(mocks.clear).not.toHaveBeenCalled();
      expect(url).toBe("/entrar");
    },
  );

  it("conta sem acesso: revoga, limpa a sessão e mostra o aviso no login", async () => {
    mocks.getRefreshToken.mockResolvedValue("rt");
    mocks.post.mockResolvedValue(ok(undefined, 204));

    const url = await redirectOf(get("?erro=acesso"));

    expect(mocks.post).toHaveBeenCalledWith("/v1/auth/logout", { body: { refresh_token: "rt" } });
    expect(mocks.clear).toHaveBeenCalled();
    expect(url).toBe("/entrar?erro=acesso");
  });

  it("sem motivo conhecido vai para o login sem aviso", async () => {
    mocks.getRefreshToken.mockResolvedValue(undefined);

    expect(await redirectOf(get("?erro=https://evil.example"))).toBe("/entrar");
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.clear).toHaveBeenCalled();
  });
});
