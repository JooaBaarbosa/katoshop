import { ApiProblem } from "@katoshop/api-client";
import { beforeEach, describe, expect, it, vi } from "vitest";

// redirect() do Next lança para interromper a renderização; o falso faz o mesmo e guarda o destino.
class RedirectSignal extends Error {
  constructor(readonly url: string) {
    super(`redirect:${url}`);
  }
}

class ForbiddenSignal extends Error {}

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  identity: vi.fn(),
  withAuth: vi.fn(),
  clear: vi.fn(),
}));

// o resto do módulo é o real: unstable_rethrow reconhece os erros internos do Next
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  redirect: (url: string) => {
    throw new RedirectSignal(url);
  },
  forbidden: () => {
    throw new ForbiddenSignal();
  },
}));

vi.mock("../lib/api", () => ({ identity: mocks.identity }));

vi.mock("../lib/session", () => ({
  session: { withAuth: mocks.withAuth, clear: mocks.clear },
}));

const { authed, requireStaff } = await import("../lib/guard");

const STAFF = {
  id: "u1",
  email: "admin@katoshop.localhost",
  name: "Admin",
  kind: "staff",
  roles: ["admin"],
};

function ok<T>(data: T) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}

async function redirectOf(promise: Promise<unknown>): Promise<string> {
  const error = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  if (!(error instanceof RedirectSignal)) throw new Error(`esperava redirect, veio ${String(error)}`);
  return error.url;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.identity.mockReturnValue({ GET: mocks.get });
  mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
});

describe("requireStaff", () => {
  it("funcionário: devolve o me lido com withAuth somente leitura", async () => {
    mocks.get.mockResolvedValue(ok(STAFF));

    const me = await requireStaff();

    expect(me).toEqual(STAFF);
    expect(mocks.identity).toHaveBeenCalledWith("at");
    expect(mocks.get).toHaveBeenCalledWith("/v1/me");
    // Server Component: sem refresh (R18); a renovação é do proxy.ts
    expect(mocks.withAuth).toHaveBeenCalledWith(expect.any(Function));
    expect(mocks.withAuth.mock.calls[0]).toHaveLength(1);
  });

  it("cliente: manda para a rota que limpa a sessão, sem gravar cookie no Server Component", async () => {
    mocks.get.mockResolvedValue(ok({ ...STAFF, kind: "customer", roles: [] }));

    const url = await redirectOf(requireStaff());

    expect(url).toBe("/sair?erro=acesso");
    expect(mocks.clear).not.toHaveBeenCalled();
  });

  it("sem sessão válida (401) vai para o login", async () => {
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 401, code: "auth.missing_token", message: "Não autenticado" }),
    );

    expect(await redirectOf(requireStaff())).toBe("/entrar");
  });

  it("token de outra audiência (403) também limpa a sessão", async () => {
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 403, code: "auth.forbidden", message: "Proibido" }),
    );

    expect(await redirectOf(requireStaff())).toBe("/sair?erro=acesso");
  });

  it("falha do identity (5xx) sobe para a página de erro", async () => {
    const outage = new ApiProblem({ status: 503, code: "http.503", message: "fora" });
    mocks.withAuth.mockRejectedValue(outage);

    await expect(requireStaff()).rejects.toBe(outage);
  });
});

describe("authed", () => {
  it("chama a API com o token sem refresh e devolve o resultado", async () => {
    const result = await authed((token) => Promise.resolve(`dados com ${token}`));

    expect(result).toBe("dados com at");
    expect(mocks.withAuth.mock.calls[0]).toHaveLength(1);
  });

  it("401 vai para o login", async () => {
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 401, code: "auth.invalid_token", message: "Token inválido" }),
    );

    expect(await redirectOf(authed(() => Promise.resolve(1)))).toBe("/entrar");
  });

  it("403 auth.forbidden (audiência errada) manda limpar a sessão", async () => {
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 403, code: "auth.forbidden", message: "Proibido" }),
    );

    expect(await redirectOf(authed(() => Promise.resolve(1)))).toBe("/sair?erro=acesso");
  });

  it("403 auth.insufficient_permission mostra a página de sem permissão, sem deslogar", async () => {
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({
        status: 403,
        code: "auth.insufficient_permission",
        message: "Requer catalog.write.",
      }),
    );

    await expect(authed(() => Promise.resolve(1))).rejects.toBeInstanceOf(ForbiddenSignal);
    expect(mocks.clear).not.toHaveBeenCalled();
  });
});
