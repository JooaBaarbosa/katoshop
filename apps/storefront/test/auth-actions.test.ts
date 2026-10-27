import { beforeEach, describe, expect, it, vi } from "vitest";

// redirect() do Next lança para interromper a action; o falso faz o mesmo e guarda o destino.
class RedirectSignal extends Error {
  constructor(readonly url: string) {
    super(`redirect:${url}`);
  }
}

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  identity: vi.fn(),
  setTokens: vi.fn(),
  clear: vi.fn(),
  withAuth: vi.fn(),
  getRefreshToken: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new RedirectSignal(url);
  },
}));

vi.mock("../lib/api", () => ({ identity: mocks.identity }));

vi.mock("../lib/session", () => ({
  session: { setTokens: mocks.setTokens, clear: mocks.clear, withAuth: mocks.withAuth },
  getRefreshToken: mocks.getRefreshToken,
}));

const { loginAction } = await import("../app/(shop)/entrar/actions");
const { registerAction } = await import("../app/(shop)/criar-conta/actions");
const { logoutAction, updateProfileAction } = await import("../app/(shop)/conta/actions");

const PAIR = {
  access_token: "at",
  refresh_token: "rt",
  expires_in: 900,
  refresh_expires_at: "2026-11-26T00:00:00Z",
  user: { id: "u1", email: "ana@exemplo.com", name: "Ana", kind: "customer", roles: [] },
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

beforeEach(() => {
  vi.clearAllMocks();
  mocks.identity.mockReturnValue({ POST: mocks.post, PATCH: mocks.patch });
});

describe("loginAction", () => {
  it("credencial inválida vira mensagem de formulário", async () => {
    mocks.post.mockResolvedValue(
      problem(401, { code: "identity.auth.invalid_credentials", title: "Credenciais inválidas" }),
    );

    const state = await loginAction(null, form({ email: "ana@exemplo.com", password: "errada" }));

    expect(state).toMatchObject({ ok: false, formError: "Email ou senha incorretos." });
    expect(mocks.setTokens).not.toHaveBeenCalled();
  });

  it("sucesso grava os tokens e redireciona para /conta", async () => {
    mocks.post.mockResolvedValue(ok(PAIR));

    const url = await redirectOf(
      loginAction(null, form({ email: "ana@exemplo.com", password: "senha-forte-123" })),
    );

    expect(mocks.post).toHaveBeenCalledWith("/v1/auth/login", {
      body: { email: "ana@exemplo.com", password: "senha-forte-123" },
    });
    expect(mocks.setTokens).toHaveBeenCalledWith(PAIR);
    expect(url).toBe("/conta");
  });

  it("respeita next interno", async () => {
    mocks.post.mockResolvedValue(ok(PAIR));

    const url = await redirectOf(
      loginAction(null, form({ email: "a@b.com", password: "x", next: "/p/camiseta?cor=PRT" })),
    );

    expect(url).toBe("/p/camiseta?cor=PRT");
  });

  it.each(["//evil.example", "https://evil.example", "/\\evil.example", "conta", "/a\\b", "/ x"])(
    "ignora next externo ou malformado (%s) e vai para /conta",
    async (next) => {
      mocks.post.mockResolvedValue(ok(PAIR));

      const url = await redirectOf(loginAction(null, form({ email: "a@b.com", password: "x", next })));

      expect(url).toBe("/conta");
    },
  );

  it("campos vazios não chamam a API", async () => {
    const state = await loginAction(null, form({ email: " ", password: "" }));

    expect(state).toMatchObject({
      ok: false,
      fieldErrors: { email: "Informe seu email.", password: "Informe sua senha." },
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("falha de rede vira mensagem genérica e preserva o email digitado", async () => {
    mocks.post.mockRejectedValue(new TypeError("fetch failed"));

    const state = await loginAction(null, form({ email: "ana@exemplo.com", password: "x" }));

    expect(state).toMatchObject({
      ok: false,
      formError: "Não foi possível concluir agora. Tente de novo em instantes.",
      values: { email: "ana@exemplo.com" },
    });
  });

  it("limite de tentativas do gateway (429) tem mensagem própria", async () => {
    mocks.post.mockResolvedValue(problem(429, {}));

    const state = await loginAction(null, form({ email: "a@b.com", password: "x" }));

    expect(state).toMatchObject({
      formError: "Muitas tentativas. Aguarde um instante e tente de novo.",
    });
  });
});

describe("registerAction", () => {
  const fields = { name: "Ana", email: "ana@exemplo.com", password: "curta" };

  it("senha fraca mostra o motivo no campo de senha", async () => {
    mocks.post.mockResolvedValue(
      problem(422, {
        code: "identity.auth.weak_password",
        title: "Senha fraca",
        errors: { "body.password": ["too_short"] },
      }),
    );

    const state = await registerAction(null, form(fields));

    expect(state).toMatchObject({ ok: false });
    expect(state?.fieldErrors?.password).toContain("Use pelo menos 10 caracteres.");
    expect(state?.values).toEqual({ name: "Ana", email: "ana@exemplo.com" });
  });

  it("vários motivos de senha fraca aparecem juntos", async () => {
    mocks.post.mockResolvedValue(
      problem(422, {
        code: "identity.auth.weak_password",
        errors: { "body.password": ["too_common", "contains_email"] },
      }),
    );

    const state = await registerAction(null, form(fields));

    expect(state?.fieldErrors?.password).toContain("Essa senha é muito comum.");
    expect(state?.fieldErrors?.password).toContain("A senha não pode conter seu email.");
  });

  it("email já cadastrado aparece no campo de email", async () => {
    mocks.post.mockResolvedValue(problem(409, { code: "identity.auth.email_taken" }));

    const state = await registerAction(null, form(fields));

    expect(state?.fieldErrors?.email).toBe("Já existe uma conta com este email.");
  });

  it("email inválido (422 de validação) aparece no campo de email", async () => {
    mocks.post.mockResolvedValue(
      problem(422, {
        code: "request.validation",
        errors: { "body.email": ["value is not a valid email address"] },
      }),
    );

    const state = await registerAction(null, form(fields));

    expect(state?.fieldErrors?.email).toBe("Informe um email válido.");
  });

  it("nome vazio não chama a API", async () => {
    const state = await registerAction(null, form({ ...fields, name: "  " }));

    expect(state?.fieldErrors?.name).toBe("Informe seu nome.");
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("sucesso grava os tokens e redireciona para /conta", async () => {
    mocks.post.mockResolvedValue(ok(PAIR, 201));

    const url = await redirectOf(
      registerAction(null, form({ ...fields, password: "senha-forte-123" })),
    );

    expect(mocks.post).toHaveBeenCalledWith("/v1/auth/register", {
      body: { name: "Ana", email: "ana@exemplo.com", password: "senha-forte-123" },
    });
    expect(mocks.setTokens).toHaveBeenCalledWith(PAIR);
    expect(url).toBe("/conta");
  });
});

describe("updateProfileAction", () => {
  beforeEach(() => {
    mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
  });

  it("usa withAuth com refresh e redireciona para /conta", async () => {
    mocks.patch.mockResolvedValue(ok(PAIR.user));

    const url = await redirectOf(updateProfileAction(null, form({ name: "Ana Souza" })));

    expect(mocks.withAuth).toHaveBeenCalledWith(expect.any(Function), { refresh: true });
    expect(mocks.identity).toHaveBeenCalledWith("at");
    expect(mocks.patch).toHaveBeenCalledWith("/v1/me", { body: { name: "Ana Souza" } });
    expect(url).toBe("/conta");
  });

  it("nome vazio não chama a API", async () => {
    const state = await updateProfileAction(null, form({ name: "" }));

    expect(state?.fieldErrors?.name).toBe("Informe seu nome.");
    expect(mocks.withAuth).not.toHaveBeenCalled();
  });

  it("sessão expirada manda para o login", async () => {
    mocks.patch.mockResolvedValue(problem(401, { code: "auth.invalid_token" }));

    const url = await redirectOf(updateProfileAction(null, form({ name: "Ana" })));

    expect(url).toBe("/entrar?next=/conta");
  });
});

describe("logoutAction", () => {
  it("revoga o refresh token, limpa a sessão e volta para a home", async () => {
    mocks.getRefreshToken.mockResolvedValue("rt");
    mocks.post.mockResolvedValue(ok(undefined, 204));

    const url = await redirectOf(logoutAction());

    expect(mocks.post).toHaveBeenCalledWith("/v1/auth/logout", { body: { refresh_token: "rt" } });
    expect(mocks.clear).toHaveBeenCalled();
    expect(url).toBe("/");
  });

  it("limpa a sessão mesmo se o identity falhar", async () => {
    mocks.getRefreshToken.mockResolvedValue("rt");
    mocks.post.mockRejectedValue(new TypeError("fetch failed"));

    const url = await redirectOf(logoutAction());

    expect(mocks.clear).toHaveBeenCalled();
    expect(url).toBe("/");
  });

  it("sem refresh token só limpa", async () => {
    mocks.getRefreshToken.mockResolvedValue(undefined);

    await redirectOf(logoutAction());

    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.clear).toHaveBeenCalled();
  });
});
