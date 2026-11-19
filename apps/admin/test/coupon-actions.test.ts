import { beforeEach, describe, expect, it, vi } from "vitest";

class RedirectSignal extends Error {
  constructor(readonly url: string) {
    super(`redirect:${url}`);
  }
}

const mocks = vi.hoisted(() => ({
  meGet: vi.fn(),
  identity: vi.fn(),
  catalog: vi.fn(),
  catalogGet: vi.fn(),
  promotions: vi.fn(),
  promoGet: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  withAuth: vi.fn(),
  clear: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  redirect: (url: string) => {
    throw new RedirectSignal(url);
  },
}));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("../lib/api", () => ({
  identity: mocks.identity,
  catalog: mocks.catalog,
  promotions: mocks.promotions,
}));
vi.mock("../lib/session", () => ({
  session: { withAuth: mocks.withAuth, clear: mocks.clear },
}));

const actions = await import("../app/(painel)/cupons/actions");
const { ApiProblem } = await import("@katoshop/api-client");

const STAFF = { id: "u1", email: "a@k.localhost", name: "Admin", kind: "staff", roles: ["admin"] };
const CID = "0190a000-0000-7000-8000-0000000000c1";

function ok<T>(data: T, status = 200) {
  return { data, error: undefined, response: new Response(null, { status }) };
}

function noContent() {
  return { data: undefined, error: undefined, response: new Response(null, { status: 204 }) };
}

function problem(status: number, body: Record<string, unknown>) {
  return { data: undefined, error: body, response: new Response(null, { status }) };
}

function form(fields: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (Array.isArray(value)) for (const item of value) data.append(key, item);
    else data.set(key, value);
  }
  return data;
}

async function redirectOf(promise: Promise<unknown>): Promise<string> {
  const error = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  if (!(error instanceof RedirectSignal))
    throw new Error(`esperava redirect, veio ${String(error)}`);
  return error.url;
}

const CREATE_FIELDS = {
  code: " bemvindo10 ",
  description: "Primeira compra",
  kind: "percent",
  value: "10",
  category_slugs: ["camisetas", "camisetas"],
  collection_slugs: ["verao"],
  active: "on",
};

const UPDATE_FIELDS = {
  id: CID,
  version: "4",
  description: "Primeira compra",
  kind: "fixed",
  value: "20,00",
  min_order: "",
  max_uses_total: "",
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.identity.mockReturnValue({ GET: mocks.meGet });
  mocks.meGet.mockResolvedValue(ok(STAFF));
  mocks.catalog.mockReturnValue({ GET: mocks.catalogGet });
  mocks.catalogGet.mockImplementation((path: string) =>
    Promise.resolve(
      path === "/v1/admin/categories"
        ? ok({ items: [{ slug: "camisetas" }, { slug: "moletons" }] })
        : ok({ items: [{ slug: "verao" }] }),
    ),
  );
  mocks.promotions.mockReturnValue({
    GET: mocks.promoGet,
    POST: mocks.post,
    PATCH: mocks.patch,
    DELETE: mocks.del,
  });
  mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
});

describe("createCouponAction", () => {
  it("slug que sumiu do catálogo vira erro no campo e não cria nada", async () => {
    const state = await actions.createCouponAction(
      null,
      form({ ...CREATE_FIELDS, category_slugs: ["camisetas", "sumiu"] }),
    );

    expect(state).toEqual({
      ok: false,
      fieldErrors: { category_slugs: "Escolha categorias da lista." },
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("422 de regra entre campos (raiz do corpo) explica no topo do formulário", async () => {
    mocks.post.mockResolvedValue(
      problem(422, {
        code: "request.validation",
        title: "Requisição inválida",
        errors: { body: ["Value error, Percentual deve ficar entre 1 e 90"] },
      }),
    );

    const state = await actions.createCouponAction(null, form(CREATE_FIELDS));

    expect(state).toEqual({
      ok: false,
      code: "request.validation",
      formError:
        "O servidor recusou a combinação de tipo, valor e datas. Confira esses campos e tente de novo.",
    });
  });

  it("envia o corpo normalizado, com slugs do catálogo, e volta à lista com aviso", async () => {
    mocks.post.mockResolvedValue(ok({ id: CID }, 201));

    const url = await redirectOf(actions.createCouponAction(null, form(CREATE_FIELDS)));

    expect(url).toBe("/cupons?aviso=criado");
    expect(mocks.promotions).toHaveBeenCalledWith("at");
    expect(mocks.post).toHaveBeenCalledWith("/v1/admin/coupons", {
      body: {
        code: "BEMVINDO10",
        description: "Primeira compra",
        kind: "percent",
        value: 10,
        min_order_cents: null,
        starts_at: null,
        ends_at: null,
        category_slugs: ["camisetas"],
        collection_slugs: ["verao"],
        max_uses_total: null,
        max_uses_per_customer: null,
        active: true,
      },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/cupons");
  });

  it("código repetido (409 code_taken) aparece no campo do código", async () => {
    mocks.post.mockResolvedValue(
      problem(409, { code: "promotions.coupon.code_taken", title: "Código de cupom já usado" }),
    );

    const state = await actions.createCouponAction(null, form(CREATE_FIELDS));

    expect(state).toEqual({
      ok: false,
      code: "promotions.coupon.code_taken",
      fieldErrors: { code: "Já existe um cupom com este código." },
    });
  });

  it("422 request.validation do servidor marca os campos do formulário", async () => {
    mocks.post.mockResolvedValue(
      problem(422, {
        code: "request.validation",
        title: "Requisição inválida",
        errors: {
          "body.value": ["Percentual deve ficar entre 1 e 90"],
          "body.min_order_cents": ["Input should be greater than or equal to 1"],
          "body.category_slugs.0": ["String should match pattern"],
          "body.ends_at": ["Fim deve ser depois do início"],
        },
      }),
    );

    const state = await actions.createCouponAction(null, form(CREATE_FIELDS));

    expect(state).toEqual({
      ok: false,
      code: "request.validation",
      formError: "Confira os campos destacados.",
      fieldErrors: {
        value: "Confira o valor: percentual inteiro de 1 a 90 ou valor fixo maior que zero.",
        min_order:
          "Informe um valor em reais maior que zero, como 99,90, até R$ 100.000,00 (limite do painel), ou deixe vazio.",
        category_slugs: "Escolha categorias da lista.",
        ends_at: "O fim deve ser depois do início.",
      },
    });
  });

  it("formulário inválido não chama a API", async () => {
    const state = await actions.createCouponAction(null, form({ ...CREATE_FIELDS, value: "95" }));

    expect(state).toEqual({
      ok: false,
      fieldErrors: { value: "Informe um percentual inteiro de 1 a 90." },
    });
    expect(mocks.withAuth).not.toHaveBeenCalled();
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("sem sessão de funcionário vai ao login e não chama a API de cupons", async () => {
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 401, code: "auth.invalid_token", message: "Token inválido" }),
    );

    expect(await redirectOf(actions.createCouponAction(null, form(CREATE_FIELDS)))).toBe("/entrar");
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.catalogGet).not.toHaveBeenCalled();
  });

  it("conta de cliente encerra a sessão e não chama a API de cupons", async () => {
    mocks.meGet.mockResolvedValue(ok({ ...STAFF, kind: "customer" }));

    expect(await redirectOf(actions.createCouponAction(null, form(CREATE_FIELDS)))).toBe(
      "/sair?erro=acesso",
    );
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("sem promotions.write (403 insufficient_permission) mostra o aviso sem deslogar", async () => {
    mocks.post.mockResolvedValue(
      problem(403, { code: "auth.insufficient_permission", title: "Permissão insuficiente" }),
    );

    const state = await actions.createCouponAction(null, form(CREATE_FIELDS));

    expect(state).toMatchObject({ ok: false, formError: "Você não tem permissão para esta ação." });
    expect(mocks.clear).not.toHaveBeenCalled();
  });
});

describe("updateCouponAction", () => {
  it("envia a versão, nunca o código nem o ativo, e volta à lista com aviso", async () => {
    mocks.patch.mockResolvedValue(ok({ id: CID, version: 5 }));

    const url = await redirectOf(
      actions.updateCouponAction(null, form({ ...UPDATE_FIELDS, code: "OUTRO", active: "on" })),
    );

    expect(url).toBe("/cupons?aviso=salvo");
    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/coupons/{coupon_id}", {
      params: { path: { coupon_id: CID } },
      body: {
        version: 4,
        description: "Primeira compra",
        kind: "fixed",
        value: 2000,
        min_order_cents: null,
        starts_at: null,
        ends_at: null,
        category_slugs: [],
        collection_slugs: [],
        max_uses_total: null,
        max_uses_per_customer: null,
      },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/cupons");
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/cupons/${CID}`);
  });

  it("slug salvo que sumiu do catálogo continua no cupom (não vira cupom da loja toda)", async () => {
    mocks.promoGet.mockResolvedValue(
      ok({ id: CID, category_slugs: ["antiga"], collection_slugs: [] }),
    );
    mocks.patch.mockResolvedValue(ok({ id: CID, version: 5 }));

    await redirectOf(
      actions.updateCouponAction(
        null,
        form({ ...UPDATE_FIELDS, category_slugs: ["antiga", "camisetas"] }),
      ),
    );

    // o cupom salvo é lido no servidor (não confiamos em campo oculto)
    expect(mocks.promoGet).toHaveBeenCalledWith("/v1/admin/coupons/{coupon_id}", {
      params: { path: { coupon_id: CID } },
    });
    const [, init] = mocks.patch.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(init.body.category_slugs).toEqual(["antiga", "camisetas"]);
  });

  it("slug novo fora do catálogo na edição vira erro no campo e não grava", async () => {
    mocks.promoGet.mockResolvedValue(
      ok({ id: CID, category_slugs: ["antiga"], collection_slugs: [] }),
    );

    const state = await actions.updateCouponAction(
      null,
      form({ ...UPDATE_FIELDS, collection_slugs: ["inventada"] }),
    );

    expect(state).toEqual({
      ok: false,
      fieldErrors: { collection_slugs: "Escolha coleções da lista." },
    });
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it("id que não é UUID não chama a API", async () => {
    const state = await actions.updateCouponAction(null, form({ ...UPDATE_FIELDS, id: "../x" }));

    expect(state).toEqual({ ok: false, formError: "Cupom não encontrado." });
    expect(mocks.withAuth).not.toHaveBeenCalled();
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it("409 de versão devolve o código e a mensagem para o botão Recarregar", async () => {
    mocks.patch.mockResolvedValue(
      problem(409, { code: "promotions.coupon.version_conflict", title: "Conflito" }),
    );

    const state = await actions.updateCouponAction(null, form(UPDATE_FIELDS));

    expect(state).toMatchObject({
      ok: false,
      code: "promotions.coupon.version_conflict",
      formError: "Este cupom foi alterado por outra pessoa. Recarregue para ver a versão atual.",
    });
  });
});

describe("ativar, desativar e excluir", () => {
  it("ativa e desativa pelas rotas próprias", async () => {
    mocks.post.mockResolvedValue(ok({ id: CID, active: true }));

    expect(await actions.activateCouponAction(CID)).toEqual({ ok: true });
    expect(await actions.deactivateCouponAction(CID)).toEqual({ ok: true });

    expect(mocks.post).toHaveBeenNthCalledWith(1, "/v1/admin/coupons/{coupon_id}/activate", {
      params: { path: { coupon_id: CID } },
    });
    expect(mocks.post).toHaveBeenNthCalledWith(2, "/v1/admin/coupons/{coupon_id}/deactivate", {
      params: { path: { coupon_id: CID } },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/cupons/${CID}`);
  });

  it("exclui e revalida a lista", async () => {
    mocks.del.mockResolvedValue(noContent());

    expect(await actions.deleteCouponAction(CID)).toEqual({ ok: true });
    expect(mocks.del).toHaveBeenCalledWith("/v1/admin/coupons/{coupon_id}", {
      params: { path: { coupon_id: CID } },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/cupons");
  });

  it("cupom com resgates (409 has_redemptions) explica e sugere desativar", async () => {
    mocks.del.mockResolvedValue(
      problem(409, { code: "promotions.coupon.has_redemptions", title: "Com resgates" }),
    );

    expect(await actions.deleteCouponAction(CID)).toEqual({
      ok: false,
      code: "promotions.coupon.has_redemptions",
      error: "Este cupom já foi usado e não pode ser excluído. Desative em vez disso.",
    });
  });

  it("id que não é UUID não chama a API", async () => {
    const notFound = { ok: false, error: "Cupom não encontrado." };
    expect(await actions.activateCouponAction("x")).toEqual(notFound);
    expect(await actions.deactivateCouponAction("x")).toEqual(notFound);
    expect(await actions.deleteCouponAction("x")).toEqual(notFound);
    expect(mocks.withAuth).not.toHaveBeenCalled();
  });

  it("sem sessão de funcionário não chama a API", async () => {
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 401, code: "auth.invalid_token", message: "Token inválido" }),
    );

    expect(await redirectOf(actions.deleteCouponAction(CID))).toBe("/entrar");
    expect(await redirectOf(actions.activateCouponAction(CID))).toBe("/entrar");
    expect(mocks.del).not.toHaveBeenCalled();
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
