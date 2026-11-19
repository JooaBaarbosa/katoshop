import { ApiProblem } from "@katoshop/api-client";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  jar: new Map<string, { value: string; options?: unknown }>(),
  get: vi.fn(),
  post: vi.fn(),
  cart: vi.fn(),
  getAccessToken: vi.fn(),
  getRefreshToken: vi.fn(),
  withAuth: vi.fn(),
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

vi.mock("../lib/api", () => ({ cart: mocks.cart }));

vi.mock("../lib/session", () => ({
  session: { getAccessToken: mocks.getAccessToken, withAuth: mocks.withAuth },
  getRefreshToken: mocks.getRefreshToken,
  sessionOptions: () => ({ secure: true }),
}));

const { CART_COOKIE, CART_FLASH_COOKIE, cartCount, cartHeaders, getCart, mergeGuestCart } =
  await import("../lib/cart");

const GUEST_ID = "3f1c2a4e-8b7d-4c1e-9a2b-5d6e7f8a9b0c";
const ACCOUNT_ID = "01a1f443-d76f-74d9-838a-33bc806544d0";

function item(quantity: number) {
  return { variant_id: "01a1f443-d7ac-7464-b08d-80647977014a", quantity, unavailable: false };
}

function cartOut(cart_id: string | null, items: ReturnType<typeof item>[] = []) {
  return {
    cart_id,
    items,
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

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, "warn").mockImplementation(() => {});
  mocks.jar.clear();
  mocks.cart.mockReturnValue({ GET: mocks.get, POST: mocks.post });
  mocks.getAccessToken.mockResolvedValue(null);
  mocks.getRefreshToken.mockResolvedValue(undefined);
  mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
});

describe("cartHeaders", () => {
  it("com sessão manda o Bearer e ignora o cookie de visitante", async () => {
    mocks.getAccessToken.mockResolvedValue("at");
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });

    await expect(cartHeaders()).resolves.toEqual({ Authorization: "Bearer at" });
  });

  it("sem sessão manda o X-Cart-Id do cookie", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });

    await expect(cartHeaders()).resolves.toEqual({ "X-Cart-Id": GUEST_ID });
  });

  it("sem sessão e sem cookie não manda nada", async () => {
    await expect(cartHeaders()).resolves.toEqual({});
  });

  it.each(["nao-e-uuid", ACCOUNT_ID, GUEST_ID.toUpperCase(), `${GUEST_ID}x`])(
    "cookie fora do formato de UUIDv4 (%s) não é enviado",
    async (value) => {
      mocks.jar.set(CART_COOKIE, { value });

      await expect(cartHeaders()).resolves.toEqual({});
    },
  );
});

describe("getCart", () => {
  it("visitante sem cookie recebe carrinho vazio sem chamar a API", async () => {
    const view = await getCart();

    expect(view).toMatchObject({ cart_id: null, items: [], unavailable: false });
    expect(mocks.get).not.toHaveBeenCalled();
  });

  it("visitante com cookie lê o carrinho pelo X-Cart-Id", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.get.mockResolvedValue(ok(cartOut(GUEST_ID, [item(2)])));

    const view = await getCart();

    expect(mocks.get).toHaveBeenCalledWith(
      "/v1/cart",
      expect.objectContaining({ headers: { "X-Cart-Id": GUEST_ID } }),
    );
    expect(view).toMatchObject({ cart_id: GUEST_ID, unavailable: false });
  });

  it("cliente lê com withAuth sem refresh (Server Component)", async () => {
    mocks.getAccessToken.mockResolvedValue("at");
    mocks.get.mockResolvedValue(ok(cartOut(ACCOUNT_ID)));

    await getCart();

    expect(mocks.withAuth).toHaveBeenCalledWith(expect.any(Function));
    expect(mocks.get).toHaveBeenCalledWith(
      "/v1/cart",
      expect.objectContaining({ headers: { Authorization: "Bearer at" } }),
    );
  });

  it("cliente com só o refresh token também usa withAuth (o 401 vira indisponível)", async () => {
    mocks.getRefreshToken.mockResolvedValue("rt");
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 401, code: "auth.missing_token", message: "Não autenticado" }),
    );

    const view = await getCart();

    expect(view.unavailable).toBe(true);
    expect(mocks.get).not.toHaveBeenCalled();
  });

  it("falha do cart devolve carrinho vazio com unavailable e não mexe no cookie", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.get.mockRejectedValue(new TypeError("fetch failed"));

    const view = await getCart();

    expect(view).toMatchObject({ items: [], unavailable: true });
    expect(mocks.jar.has(CART_COOKIE)).toBe(true);
  });
});

describe("cartCount", () => {
  it("soma as quantidades", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.get.mockResolvedValue(ok(cartOut(GUEST_ID, [item(2), item(1)])));

    await expect(cartCount()).resolves.toBe(3);
  });

  it("carrinho indisponível devolve null (o cabeçalho mostra só 'Carrinho')", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.get.mockResolvedValue(problem(503, { code: "cart.storage.unavailable" }));

    await expect(cartCount()).resolves.toBeNull();
  });
});

describe("mergeGuestCart", () => {
  const merged = (reduced: string[] = [], dropped: string[] = []) =>
    ok({ ...cartOut(ACCOUNT_ID), merge_report: { reduced, dropped } });

  it("sem cookie não chama a API", async () => {
    await mergeGuestCart("novo-at");

    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("une com o token novo e apaga o cookie", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.post.mockResolvedValue(merged());

    await mergeGuestCart("novo-at");

    expect(mocks.cart).toHaveBeenCalledWith("novo-at");
    expect(mocks.post).toHaveBeenCalledWith(
      "/v1/cart/merge",
      expect.objectContaining({ body: { guest_cart_id: GUEST_ID } }),
    );
    expect(mocks.jar.has(CART_COOKIE)).toBe(false);
    expect(mocks.jar.has(CART_FLASH_COOKIE)).toBe(false);
  });

  it("itens ajustados no merge deixam o aviso curto para o /carrinho", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.post.mockResolvedValue(merged(["v1"], []));

    await mergeGuestCart("novo-at");

    const flash = mocks.jar.get(CART_FLASH_COOKIE);
    expect(flash?.value).toBe("merge_adjusted");
    expect(flash?.options).toMatchObject({
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure: true,
    });
  });

  it("falha no merge mantém o cookie e não lança", async () => {
    mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
    mocks.post.mockResolvedValue(problem(503, { code: "cart.storage.unavailable" }));

    await expect(mergeGuestCart("novo-at")).resolves.toBeUndefined();

    expect(mocks.jar.get(CART_COOKIE)?.value).toBe(GUEST_ID);
  });

  it("cookie malformado é apagado sem chamar a API", async () => {
    mocks.jar.set(CART_COOKIE, { value: "lixo" });

    await mergeGuestCart("novo-at");

    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.jar.has(CART_COOKIE)).toBe(false);
  });
});
