import { ApiProblem } from "@katoshop/api-client";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

  it.each(["Token emitido para outra audiência.", "Permissão insuficiente."])(
    "403 auth.forbidden encerra a sessão pelo código, seja qual for o detalhe (%s)",
    async (detail) => {
      const write = vi
        .fn()
        .mockRejectedValue(new ApiProblem({ status: 403, code: "auth.forbidden", message: detail }));

      expect(await redirectOf(staffAction(write))).toBe("/sair?erro=acesso");
    },
  );

  it("403 auth.insufficient_permission numa escrita mostra a mensagem sem deslogar", async () => {
    const write = vi.fn().mockRejectedValue(
      new ApiProblem({
        status: 403,
        code: "auth.insufficient_permission",
        message: "Requer catalog.write.",
      }),
    );

    const result = await staffAction(write);

    expect(result).toEqual({
      ok: false,
      code: "auth.insufficient_permission",
      error: PERMISSION_DENIED,
    });
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

  it("falha inesperada vira mensagem genérica e é registrada no log", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const failure = new TypeError("fetch failed");
    const write = vi.fn().mockRejectedValue(failure);

    const result = await staffAction(write);

    expect(result).toMatchObject({ ok: false });
    expect(result.ok === false && result.error).toContain("Algo deu errado");
    expect(log).toHaveBeenCalledWith(expect.any(String), failure);
    log.mockRestore();
  });

  it("5xx da API é registrado com o trace id", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const outage = new ApiProblem({
      status: 500,
      code: "internal.error",
      message: "Erro interno",
      traceId: "trace-42",
    });
    const write = vi.fn().mockRejectedValue(outage);

    const result = await staffAction(write);

    expect(result.ok === false && result.error).toBe("Algo deu errado. Código para suporte: trace-42");
    expect(log).toHaveBeenCalledWith(expect.stringContaining("trace-42"), outage);
    log.mockRestore();
  });

  it("redirect e notFound lançados dentro da escrita sobem para o Next", async () => {
    const real = await vi.importActual<typeof import("next/navigation")>("next/navigation");

    const redirected = await staffAction(() => real.redirect("/produtos/novo-id")).then(
      () => null,
      (e: unknown) => e,
    );
    const missing = await staffAction(() => real.notFound()).then(
      () => null,
      (e: unknown) => e,
    );

    expect((redirected as { digest?: string }).digest).toContain("NEXT_REDIRECT");
    expect((redirected as { digest?: string }).digest).toContain("/produtos/novo-id");
    expect((missing as { digest?: string }).digest).toContain("404");
  });
});
