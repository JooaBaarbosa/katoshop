import { ApiProblem } from "@katoshop/api-client";
import { beforeEach, describe, expect, it, vi } from "vitest";

class RedirectSignal extends Error {
  constructor(readonly url: string) {
    super(`redirect:${url}`);
  }
}

const mocks = vi.hoisted(() => ({
  jar: new Map<string, { value: string; options?: unknown }>(),
  cartPost: vi.fn(),
  cart: vi.fn(),
  identityPost: vi.fn(),
  identity: vi.fn(),
  getAccessToken: vi.fn(),
  getRefreshToken: vi.fn(),
  withAuth: vi.fn(),
  setTokens: vi.fn(),
  revalidatePath: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        mocks.jar.has(name) ? { name, value: mocks.jar.get(name)?.value } : undefined,
      set: (name: string, value: string, options?: unknown) => {
        mocks.jar.set(name, { value, options });
      },
      delete: (name: string) => {
        mocks.jar.delete(name);
      },
    }),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath, refresh: mocks.refresh }));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new RedirectSignal(url);
  },
}));

vi.mock("../lib/api", () => ({ cart: mocks.cart, identity: mocks.identity }));

vi.mock("../lib/session", () => ({
  session: {
    getAccessToken: mocks.getAccessToken,
    withAuth: mocks.withAuth,
    setTokens: mocks.setTokens,
  },
  getRefreshToken: mocks.getRefreshToken,
  sessionOptions: () => ({ secure: true }),
}));

const { addToCartAction } = await import("../app/(shop)/cart-actions");
const { loginAction } = await import("../app/(shop)/entrar/actions");
const { registerAction } = await import("../app/(shop)/criar-conta/actions");
const { CART_COOKIE } = await import("../lib/cart");

const VARIANT = "01a1f443-d7ac-7464-b08d-80647977014a";
const GUEST_ID = "3f1c2a4e-8b7d-4c1e-9a2b-5d6e7f8a9b0c";
const NEW_GUEST_ID = "9b2d7c1a-4e5f-4a6b-8c7d-0e1f2a3b4c5d";
const ACCOUNT_ID = "01a1f443-d76f-74d9-838a-33bc806544d0";

const PAIR = {
  access_token: "novo-at",
  refresh_token: "rt",
  expires_in: 900,
  refresh_expires_at: "2026-11-26T00:00:00Z",
  user: { id: "u1", email: "ana@exemplo.com", name: "Ana", kind: "customer", roles: [] },
};

function cartOut(cart_id: string | null) {
  return {
    cart_id,
    items: [],
    subtotal_cents: 0,
    discount_cents: 0,
    total_cents: 0,
    coupon: null,
    checkout_blocked: false,
  };
}

function ok<T>(data: T) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}

function problem(status: number, body: Record<string, unknown>) {
  return { data: undefined, error: body, response: new Response(null, { status }) };
}

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

const addForm = () => form({ variant_id: VARIANT, quantity: "1" });

async function redirectOf(action: Promise<unknown>): Promise<string> {
  const error = await action.then(
    () => null,
    (e: unknown) => e,
  );
  if (!(error instanceof RedirectSignal))
    throw new Error(`esperava redirect, veio ${String(error)}`);
  return error.url;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, "warn").mockImplementation(() => {});
  mocks.jar.clear();
  mocks.cart.mockReturnValue({ POST: mocks.cartPost });
  mocks.identity.mockReturnValue({ POST: mocks.identityPost });
  mocks.getAccessToken.mockResolvedValue(null);
  mocks.getRefreshToken.mockResolvedValue(undefined);
  mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
});

describe("addToCartAction", () => {
  it("visitante novo: grava o ks_cart com o cart_id devolvido", async () => {
    mocks.cartPost.mockResolvedValue(ok(cartOut(NEW_GUEST_ID)));

    const state = await addToCartAction(null, addForm());

    expect(state).toEqual({ ok: true });
    expect(mocks.cartPost).toHaveBeenCalledWith(
      "/v1/cart/items",
      expect.objectContaining({ body: { variant_id: VARIANT, quantity: 1 }, headers: {} }),
    );
    expect(mocks.jar.get(CART_COOKIE)).toEqual({
      value: NEW_GUEST_ID,
      options: { httpOnly: true, sameSite: "lax", path: "/", maxAge: 2592000, secure: true },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/carrinho");
  });

  it("visitante com carrinho: manda o X-Cart-Id e não regrava o cookie", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.cartPost.mockResolvedValue(ok(cartOut(GUEST_ID)));

    await addToCartAction(null, addForm());

    expect(mocks.cartPost).toHaveBeenCalledWith(
      "/v1/cart/items",
      expect.objectContaining({ headers: { "X-Cart-Id": GUEST_ID } }),
    );
    expect(mocks.jar.get(CART_COOKIE)).toEqual({ value: GUEST_ID });
  });

  it("cookie de um carrinho que expirou é trocado pelo carrinho novo", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.cartPost.mockResolvedValue(ok(cartOut(NEW_GUEST_ID)));

    await addToCartAction(null, addForm());

    expect(mocks.jar.get(CART_COOKIE)?.value).toBe(NEW_GUEST_ID);
  });

  it("cookie malformado não é enviado e é substituído", async () => {
    mocks.jar.set(CART_COOKIE, { value: "lixo" });
    mocks.cartPost.mockResolvedValue(ok(cartOut(NEW_GUEST_ID)));

    await addToCartAction(null, addForm());

    expect(mocks.cartPost).toHaveBeenCalledWith(
      "/v1/cart/items",
      expect.objectContaining({ headers: {} }),
    );
    expect(mocks.jar.get(CART_COOKIE)?.value).toBe(NEW_GUEST_ID);
  });

  it("cart recusando o id (invalid_id) apaga o cookie", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.cartPost.mockResolvedValue(problem(422, { code: "cart.cart.invalid_id" }));

    const state = await addToCartAction(null, addForm());

    expect(state?.ok).toBe(false);
    expect(mocks.jar.has(CART_COOKIE)).toBe(false);
  });

  it("cliente: withAuth com refresh, Bearer e nenhum cookie de visitante", async () => {
    mocks.getAccessToken.mockResolvedValue("at");
    mocks.cartPost.mockResolvedValue(ok(cartOut(ACCOUNT_ID)));

    const state = await addToCartAction(null, addForm());

    expect(state).toEqual({ ok: true });
    expect(mocks.withAuth).toHaveBeenCalledWith(expect.any(Function), { refresh: true });
    expect(mocks.cartPost).toHaveBeenCalledWith(
      "/v1/cart/items",
      expect.objectContaining({ headers: { Authorization: "Bearer at" } }),
    );
    expect(mocks.jar.has(CART_COOKIE)).toBe(false);
  });

  it("cliente com só o refresh token também vai pelo withAuth", async () => {
    mocks.getRefreshToken.mockResolvedValue("rt");
    mocks.cartPost.mockResolvedValue(ok(cartOut(ACCOUNT_ID)));

    await addToCartAction(null, addForm());

    expect(mocks.withAuth).toHaveBeenCalledWith(expect.any(Function), { refresh: true });
    expect(mocks.jar.has(CART_COOKIE)).toBe(false);
  });

  it.each([
    [3, "Só temos 3 unidades desse tamanho."],
    [1, "Só temos 1 unidade desse tamanho."],
  ])("estoque insuficiente (max %i) mostra quanto há", async (max, message) => {
    mocks.cartPost.mockResolvedValue(
      problem(422, { code: "cart.item.quantity_exceeds_stock", max }),
    );

    const state = await addToCartAction(null, addForm());

    expect(state).toEqual({ ok: false, message, max });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it.each([
    [
      { code: "cart.item.quantity_limit", max: 20 },
      "Você pode levar até 20 unidades de cada item.",
    ],
    [
      { code: "cart.cart.too_many_lines", max: 30 },
      "Seu carrinho chegou ao limite de 30 itens diferentes.",
    ],
    [{ code: "cart.item.unavailable" }, "Esse item não está mais disponível."],
    [{ code: "cart.item.not_found" }, "Esse item não está mais disponível."],
    [
      { code: "cart.catalog.unavailable" },
      "Não foi possível adicionar agora. Tente de novo em instantes.",
    ],
    [{ code: "algo.inesperado" }, "Não foi possível concluir agora. Tente de novo em instantes."],
  ])("mensagem pt-BR por código (%o)", async (body, message) => {
    mocks.cartPost.mockResolvedValue(
      problem(body.code === "cart.catalog.unavailable" ? 503 : 422, body),
    );

    const state = await addToCartAction(null, addForm());

    expect(state).toMatchObject({ ok: false, message });
  });

  it("sessão expirada pede para entrar de novo", async () => {
    mocks.getAccessToken.mockResolvedValue("at");
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 401, code: "auth.session_expired", message: "Sessão expirada" }),
    );

    const state = await addToCartAction(null, addForm());

    expect(state).toEqual({
      ok: false,
      message: "Sua sessão expirou. Entre de novo para continuar.",
    });
  });

  it("falha de rede vira a mensagem de tente de novo", async () => {
    mocks.cartPost.mockRejectedValue(new TypeError("fetch failed"));

    const state = await addToCartAction(null, addForm());

    expect(state).toEqual({
      ok: false,
      message: "Não foi possível adicionar agora. Tente de novo em instantes.",
    });
  });

  it.each([
    { variant_id: "", quantity: "1" },
    { variant_id: "nao-e-uuid", quantity: "1" },
    { variant_id: VARIANT, quantity: "0" },
    { variant_id: VARIANT, quantity: "1.5" },
    { variant_id: VARIANT, quantity: "abc" },
  ])("entrada inválida (%o) não chama a API", async (fields) => {
    const state = await addToCartAction(null, form(fields));

    expect(state?.ok).toBe(false);
    expect(mocks.cartPost).not.toHaveBeenCalled();
  });

  it("variant_id em maiúsculas é normalizado", async () => {
    mocks.cartPost.mockResolvedValue(ok(cartOut(NEW_GUEST_ID)));

    await addToCartAction(null, form({ variant_id: VARIANT.toUpperCase(), quantity: "2" }));

    expect(mocks.cartPost).toHaveBeenCalledWith(
      "/v1/cart/items",
      expect.objectContaining({ body: { variant_id: VARIANT, quantity: 2 } }),
    );
  });
});

describe("merge no login e no cadastro", () => {
  const merged = ok({ ...cartOut(ACCOUNT_ID), merge_report: { reduced: [], dropped: [] } });

  it("login com ks_cart chama o merge com o token novo e apaga o cookie", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.identityPost.mockResolvedValue(ok(PAIR));
    mocks.cartPost.mockResolvedValue(merged);

    const url = await redirectOf(loginAction(null, form({ email: "a@b.com", password: "x" })));

    expect(url).toBe("/conta");
    expect(mocks.setTokens).toHaveBeenCalledWith(PAIR);
    expect(mocks.cart).toHaveBeenCalledWith("novo-at");
    expect(mocks.cartPost).toHaveBeenCalledWith(
      "/v1/cart/merge",
      expect.objectContaining({ body: { guest_cart_id: GUEST_ID } }),
    );
    expect(mocks.jar.has(CART_COOKIE)).toBe(false);
  });

  it("merge falhando mantém o cookie e o login continua", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.identityPost.mockResolvedValue(ok(PAIR));
    mocks.cartPost.mockRejectedValue(new TypeError("fetch failed"));

    const url = await redirectOf(loginAction(null, form({ email: "a@b.com", password: "x" })));

    expect(url).toBe("/conta");
    expect(mocks.setTokens).toHaveBeenCalledWith(PAIR);
    expect(mocks.jar.get(CART_COOKIE)?.value).toBe(GUEST_ID);
  });

  it("login sem ks_cart não chama o cart", async () => {
    mocks.identityPost.mockResolvedValue(ok(PAIR));

    await redirectOf(loginAction(null, form({ email: "a@b.com", password: "x" })));

    expect(mocks.cartPost).not.toHaveBeenCalled();
  });

  it("login recusado não tenta o merge", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.identityPost.mockResolvedValue(
      problem(401, { code: "identity.auth.invalid_credentials" }),
    );

    await loginAction(null, form({ email: "a@b.com", password: "x" }));

    expect(mocks.cartPost).not.toHaveBeenCalled();
    expect(mocks.jar.get(CART_COOKIE)?.value).toBe(GUEST_ID);
  });

  it("cadastro com ks_cart também une o carrinho", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.identityPost.mockResolvedValue(ok(PAIR));
    mocks.cartPost.mockResolvedValue(merged);

    const url = await redirectOf(
      registerAction(null, form({ name: "Ana", email: "a@b.com", password: "senha-forte-123" })),
    );

    expect(url).toBe("/conta");
    expect(mocks.cart).toHaveBeenCalledWith("novo-at");
    expect(mocks.jar.has(CART_COOKIE)).toBe(false);
  });
});
