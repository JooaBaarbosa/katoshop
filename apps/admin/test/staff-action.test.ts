import { ApiProblem } from "@katoshop/api-client";
import { beforeEach, describe, expect, it, vi } from "vitest";

class RedirectSignal extends Error {
  constructor(readonly url: string) {
    super(`redirect:${url}`);
  }
}

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  identity: vi.fn(),
  withAuth: vi.fn(),
  clear: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new RedirectSignal(url);
  },
}));
vi.mock("../lib/api", () => ({ identity: mocks.identity }));
vi.mock("../lib/session", () => ({
  session: { withAuth: mocks.withAuth, clear: mocks.clear },
}));

const { staffAction, PERMISSION_DENIED } = await import("../lib/staff-action");

const STAFF = { id: "u1", email: "a@k.localhost", name: "Admin", kind: "staff", roles: ["admin"] };

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
  mocks.get.mockResolvedValue(ok(STAFF));
  mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
});

describe("staffAction", () => {
  it("confere o funcionário com refresh habilitado (Server Action, R18) e devolve os dados", async () => {
    const write = vi.fn().mockResolvedValue("feito");

    const result = await staffAction(write);

    expect(result).toEqual({ ok: true, data: "feito" });
    expect(mocks.withAuth).toHaveBeenCalledWith(expect.any(Function), { refresh: true });
    expect(mocks.get).toHaveBeenCalledWith("/v1/me");
    expect(write).toHaveBeenCalledWith("at");
  });

  it("sem sessão de funcionário (401) vai ao login e não escreve", async () => {
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 401, code: "auth.missing_token", message: "Não autenticado" }),
    );
    const write = vi.fn();

    expect(await redirectOf(staffAction(write))).toBe("/entrar");
    expect(write).not.toHaveBeenCalled();
  });

  it("conta que não é de funcionário encerra a sessão e não escreve", async () => {
    mocks.get.mockResolvedValue(ok({ ...STAFF, kind: "customer" }));
    const write = vi.fn();

    expect(await redirectOf(staffAction(write))).toBe("/sair?erro=acesso");
    expect(write).not.toHaveBeenCalled();
  });

  it("403 de audiência errada encerra a sessão", async () => {
    const write = vi.fn().mockRejectedValue(
      new ApiProblem({
        status: 403,
        code: "auth.forbidden",
        message: "Token emitido para outra audiência.",
      }),
    );

    expect(await redirectOf(staffAction(write))).toBe("/sair?erro=acesso");
  });

  it("403 de permissão numa escrita mostra a mensagem sem deslogar", async () => {
    const write = vi.fn().mockRejectedValue(
      new ApiProblem({ status: 403, code: "auth.forbidden", message: "Permissão insuficiente." }),
    );

    const result = await staffAction(write);

    expect(result).toEqual({ ok: false, code: "auth.forbidden", error: PERMISSION_DENIED });
    expect(PERMISSION_DENIED).toBe("Você não tem permissão para esta ação.");
    expect(mocks.clear).not.toHaveBeenCalled();
  });

  it("problema de negócio vira mensagem pelo código", async () => {
    const write = vi.fn().mockRejectedValue(
      new ApiProblem({ status: 409, code: "catalog.category.in_use", message: "Em uso" }),
    );

    expect(await staffAction(write)).toEqual({
      ok: false,
      code: "catalog.category.in_use",
      error: "Há produtos nesta categoria.",
    });
  });

  it("422 de validação devolve os campos com erro", async () => {
    const write = vi.fn().mockRejectedValue(
      new ApiProblem({
        status: 422,
        code: "request.validation",
        message: "Requisição inválida",
        errors: { name: ["campo obrigatório"] },
      }),
    );

    const result = await staffAction(write);

    expect(result).toMatchObject({ ok: false, code: "request.validation" });
    expect(result.ok === false && result.fieldErrors).toEqual({ name: "campo obrigatório" });
  });

  it("falha de rede vira mensagem genérica", async () => {
    const write = vi.fn().mockRejectedValue(new TypeError("fetch failed"));

    const result = await staffAction(write);

    expect(result).toMatchObject({ ok: false });
    expect(result.ok === false && result.error).toContain("Algo deu errado");
  });
});
