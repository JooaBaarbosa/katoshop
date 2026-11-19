import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

const mocks = vi.hoisted(() => ({
  jar: new Map<string, { value: string; options?: unknown }>(),
  cartGet: vi.fn(),
  cartPost: vi.fn(),
  cartPut: vi.fn(),
  cartPatch: vi.fn(),
  cartDelete: vi.fn(),
  cart: vi.fn(),
  getAccessToken: vi.fn(),
  getRefreshToken: vi.fn(),
  withAuth: vi.fn(),
  revalidatePath: vi.fn(),
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

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath, refresh: vi.fn() }));

vi.mock("../lib/api", () => ({ cart: mocks.cart }));

vi.mock("../lib/session", () => ({
  session: { getAccessToken: mocks.getAccessToken, withAuth: mocks.withAuth },
  getRefreshToken: mocks.getRefreshToken,
  sessionOptions: () => ({ secure: true }),
}));

const actions = await import("../app/(shop)/carrinho/actions");
const { default: CartPage } = await import("../app/(shop)/carrinho/page");
const { CART_COOKIE, CART_FLASH_COOKIE } = await import("../lib/cart");

const GUEST_ID = "3f1c2a4e-8b7d-4c1e-9a2b-5d6e7f8a9b0c";
const VARIANT = "01a1f443-d7ac-7464-b08d-80647977014a";
const OTHER = "01a1f443-d7ac-7464-b08d-80647977014b";

type Item = Record<string, unknown>;

function item(overrides: Item = {}): Item {
  return {
    variant_id: VARIANT,
    product_id: "01a1f443-0000-7000-8000-000000000001",
    product_slug: "moletom-zip",
    name: "Moletom Zip",
    color_code: "PRT",
    color_name: "Preto",
    size_code: "M",
    image_url: null,
    unit_price_cents: 14990,
    available: 5,
    quantity: 2,
    line_discount_cents: 0,
    unavailable: false,
    notice: null,
    ...overrides,
  };
}

function cartOut(overrides: Record<string, unknown> = {}) {
  return {
    cart_id: GUEST_ID,
    items: [],
    subtotal_cents: 0,
    discount_cents: 0,
    total_cents: 0,
    coupon: null,
    checkout_blocked: false,
    ...overrides,
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

// NBSP do Intl.NumberFormat (escrito por código: o lint recusa o caractere literal)
const NBSP = String.fromCharCode(0xa0);
const plain = (html: string) => html.replaceAll(NBSP, " ").replace(/&nbsp;|&#xA0;/g, " ");

async function renderPage(): Promise<string> {
  return plain(renderToStaticMarkup(await CartPage()));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, "warn").mockImplementation(() => {});
  mocks.jar.clear();
  mocks.jar.set(CART_COOKIE, { value: GUEST_ID });
  mocks.cart.mockReturnValue({
    GET: mocks.cartGet,
    POST: mocks.cartPost,
    PUT: mocks.cartPut,
    PATCH: mocks.cartPatch,
    DELETE: mocks.cartDelete,
  });
  mocks.getAccessToken.mockResolvedValue(null);
  mocks.getRefreshToken.mockResolvedValue(undefined);
  mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
});

describe("applyCouponAction", () => {
  it("422 cart.coupon.invalid mostra o motivo em pt-BR e mantém o código digitado", async () => {
    mocks.cartPut.mockResolvedValue(
      problem(422, {
        code: "cart.coupon.invalid",
        reason: "promotions.coupon.min_order_not_met",
        min_order_cents: 20000,
      }),
    );

    const state = await actions.applyCouponAction(null, form({ code: " bemvindo10 " }));

    expect(state).toMatchObject({ ok: false, code: "bemvindo10" });
    expect(plain(state?.message ?? "")).toBe(
      "Pedido mínimo de R$ 200,00 em itens válidos para este cupom.",
    );
    expect(mocks.cartPut).toHaveBeenCalledWith(
      "/v1/cart/coupon",
      expect.objectContaining({ body: { code: "bemvindo10" }, headers: { "X-Cart-Id": GUEST_ID } }),
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/carrinho");
  });

  it("422 com outro motivo usa a tabela de mensagens", async () => {
    mocks.cartPut.mockResolvedValue(
      problem(422, { code: "cart.coupon.invalid", reason: "promotions.coupon.expired" }),
    );

    const state = await actions.applyCouponAction(null, form({ code: "VERAO" }));

    expect(state?.message).toBe("Este cupom expirou.");
  });

  it("503 do promotions mostra que não deu para validar e mantém o código", async () => {
    mocks.cartPut.mockResolvedValue(problem(503, { code: "cart.promotions.unavailable" }));

    const state = await actions.applyCouponAction(null, form({ code: "VERAO" }));

    expect(state).toEqual({
      ok: false,
      code: "VERAO",
      message: "Não foi possível validar o cupom agora.",
    });
  });

  it("sucesso limpa o campo", async () => {
    mocks.cartPut.mockResolvedValue(ok(cartOut()));

    await expect(actions.applyCouponAction(null, form({ code: "VERAO" }))).resolves.toEqual({
      ok: true,
    });
  });

  it("campo vazio não chama o cart", async () => {
    const state = await actions.applyCouponAction(null, form({ code: "  " }));

    expect(state).toEqual({ ok: false, code: "", message: "Digite o código do cupom." });
    expect(mocks.cartPut).not.toHaveBeenCalled();
  });

  it("cliente usa withAuth com refresh (R18)", async () => {
    mocks.getAccessToken.mockResolvedValue("at");
    mocks.cartPut.mockResolvedValue(ok(cartOut()));

    await actions.applyCouponAction(null, form({ code: "VERAO" }));

    expect(mocks.withAuth).toHaveBeenCalledWith(expect.any(Function), { refresh: true });
    expect(mocks.cartPut).toHaveBeenCalledWith(
      "/v1/cart/coupon",
      expect.objectContaining({ headers: { Authorization: "Bearer at" } }),
    );
  });
});

describe("updateQuantityAction e removeItemAction", () => {
  it("PATCH com a nova quantidade", async () => {
    mocks.cartPatch.mockResolvedValue(ok(cartOut()));

    const state = await actions.updateQuantityAction(
      null,
      form({ variant_id: VARIANT, quantity: "3" }),
    );

    expect(state).toEqual({ ok: true });
    expect(mocks.cartPatch).toHaveBeenCalledWith(
      "/v1/cart/items/{variant_id}",
      expect.objectContaining({
        params: { path: { variant_id: VARIANT } },
        body: { quantity: 3 },
      }),
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/carrinho");
  });

  it("estoque insuficiente aparece em linha com o máximo", async () => {
    mocks.cartPatch.mockResolvedValue(
      problem(422, { code: "cart.item.quantity_exceeds_stock", max: 2 }),
    );

    const state = await actions.updateQuantityAction(
      null,
      form({ variant_id: VARIANT, quantity: "3" }),
    );

    expect(state).toEqual({ ok: false, message: "Só temos 2 unidades desse tamanho.", max: 2 });
  });

  it("falha de rede usa mensagem de carrinho, não de adicionar", async () => {
    mocks.cartPatch.mockRejectedValue(new TypeError("fetch failed"));

    const state = await actions.updateQuantityAction(
      null,
      form({ variant_id: VARIANT, quantity: "3" }),
    );

    expect(state).toEqual({
      ok: false,
      message: "Não foi possível atualizar o carrinho agora. Tente de novo em instantes.",
    });
  });

  it.each([
    { variant_id: "nao-e-uuid", quantity: "1" },
    { variant_id: VARIANT, quantity: "0" },
    { variant_id: VARIANT, quantity: "21" },
    { variant_id: VARIANT, quantity: "1.5" },
  ])("entrada inválida %o não chama o cart", async (fields) => {
    const state = await actions.updateQuantityAction(null, form(fields));

    expect(state?.ok).toBe(false);
    expect(mocks.cartPatch).not.toHaveBeenCalled();
  });

  it("remover chama o DELETE do item", async () => {
    mocks.cartDelete.mockResolvedValue(ok(cartOut()));

    const state = await actions.removeItemAction(null, form({ variant_id: VARIANT }));

    expect(state).toEqual({ ok: true });
    expect(mocks.cartDelete).toHaveBeenCalledWith(
      "/v1/cart/items/{variant_id}",
      expect.objectContaining({ params: { path: { variant_id: VARIANT } } }),
    );
  });
});

describe("ações de botão (useActionState)", () => {
  it("removeUnavailableAction chama o DELETE dos indisponíveis", async () => {
    mocks.cartDelete.mockResolvedValue(ok(cartOut()));

    await expect(actions.removeUnavailableAction()).resolves.toEqual({
      ok: true,
    });

    expect(mocks.cartDelete).toHaveBeenCalledWith(
      "/v1/cart/items/unavailable",
      expect.objectContaining({ headers: { "X-Cart-Id": GUEST_ID } }),
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/carrinho");
  });

  it("removeCouponAction chama o DELETE do cupom", async () => {
    mocks.cartDelete.mockResolvedValue(ok(cartOut()));

    await expect(actions.removeCouponAction()).resolves.toEqual({ ok: true });

    expect(mocks.cartDelete).toHaveBeenCalledWith("/v1/cart/coupon", expect.anything());
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/carrinho");
  });

  it.each([
    ["removeUnavailableAction", () => mocks.cartDelete],
    ["removeCouponAction", () => mocks.cartDelete],
    ["ackNoticesAction", () => mocks.cartPost],
  ] as const)("%s com falha devolve a mensagem para o role=status", async (name, call) => {
    call().mockRejectedValue(new TypeError("fetch failed"));

    const state = await actions[name]();

    expect(state).toEqual({
      ok: false,
      message: "Não foi possível atualizar o carrinho agora. Tente de novo em instantes.",
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/carrinho");
  });

  it("concorrência mostra a mensagem do cart", async () => {
    mocks.cartDelete.mockResolvedValue(problem(409, { code: "cart.cart.concurrent_update" }));

    const state = await actions.removeCouponAction();

    expect(state).toEqual({
      ok: false,
      message: "Seu carrinho mudou em outra aba. Tente de novo.",
    });
  });

  it("ackNoticesAction limpa os avisos e o flash do merge", async () => {
    mocks.jar.set(CART_FLASH_COOKIE, { value: "merge_adjusted" });
    mocks.cartPost.mockResolvedValue(ok(cartOut()));

    await expect(actions.ackNoticesAction()).resolves.toEqual({ ok: true });

    expect(mocks.cartPost).toHaveBeenCalledWith("/v1/cart/notices/ack", expect.anything());
    expect(mocks.jar.has(CART_FLASH_COOKIE)).toBe(false);
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/carrinho");
  });

  it("ackNoticesAction com o cart fora ainda limpa o flash", async () => {
    mocks.jar.set(CART_FLASH_COOKIE, { value: "merge_adjusted" });
    mocks.cartPost.mockRejectedValue(new TypeError("fetch failed"));

    const state = await actions.ackNoticesAction();

    expect(state?.ok).toBe(false);
    expect(mocks.jar.has(CART_FLASH_COOKIE)).toBe(false);
  });
});

type RenderedForm = { html: string; fields: Record<string, string> };

/** Os formulários do HTML renderizado com os campos que o navegador enviaria (inputs nomeados). */
function formsOf(html: string): RenderedForm[] {
  return [...html.matchAll(/<form[^>]*>([\s\S]*?)<\/form>/g)].map(([whole, inner = ""]) => {
    const fields: Record<string, string> = {};
    for (const [input] of inner.matchAll(/<input[^>]*>/g)) {
      const name = /\sname="([^"]*)"/.exec(input)?.[1];
      const value = /\svalue="([^"]*)"/.exec(input)?.[1] ?? "";
      if (name) fields[name] = value;
    }
    return { html: whole, fields };
  });
}

function formWith(forms: RenderedForm[], marker: string): RenderedForm {
  const found = forms.find((f) => f.html.includes(marker));
  if (!found) throw new Error(`nenhum formulário com ${marker}`);
  return found;
}

describe("formulários da linha (o que o navegador envia)", () => {
  async function lineForms() {
    mocks.cartGet.mockResolvedValue(ok(cartOut({ items: [item({ quantity: 2, available: 5 })] })));
    return formsOf(await renderPage());
  }

  it("− e + ficam em formulários próprios com variant_id e a quantidade-alvo em inputs", async () => {
    const forms = await lineForms();

    expect(formWith(forms, 'aria-label="Diminuir quantidade"').fields).toMatchObject({
      variant_id: VARIANT,
      quantity: "1",
    });
    expect(formWith(forms, 'aria-label="Aumentar quantidade"').fields).toMatchObject({
      variant_id: VARIANT,
      quantity: "3",
    });
  });

  it("os botões não dependem de name/value do submitter", async () => {
    const forms = await lineForms();
    for (const marker of ['aria-label="Diminuir quantidade"', 'aria-label="Aumentar quantidade"']) {
      const button = /<button[^>]*>/.exec(formWith(forms, marker).html)?.[0] ?? "";
      expect(button).not.toMatch(/\sname="quantity"/);
    }
  });

  it("o FormData do + chega ao updateQuantityAction com a quantidade", async () => {
    const forms = await lineForms();
    mocks.cartPatch.mockResolvedValue(ok(cartOut()));

    const state = await actions.updateQuantityAction(
      null,
      form(formWith(forms, 'aria-label="Aumentar quantidade"').fields),
    );

    expect(state?.ok).toBe(true);
    expect(mocks.cartPatch).toHaveBeenCalledWith(
      "/v1/cart/items/{variant_id}",
      expect.objectContaining({
        params: { path: { variant_id: VARIANT } },
        body: { quantity: 3 },
      }),
    );
  });

  it("Remover fica num formulário separado e chega ao removeItemAction", async () => {
    const forms = await lineForms();
    const remove = formWith(forms, "Remover");
    expect(remove.fields.quantity).toBeUndefined();
    mocks.cartDelete.mockResolvedValue(ok(cartOut()));

    await actions.removeItemAction(null, form(remove.fields));

    expect(mocks.cartDelete).toHaveBeenCalledWith(
      "/v1/cart/items/{variant_id}",
      expect.objectContaining({ params: { path: { variant_id: VARIANT } } }),
    );
  });

  it("a quantidade exibida tem nome acessível", async () => {
    mocks.cartGet.mockResolvedValue(ok(cartOut({ items: [item()] })));

    expect(await renderPage()).toMatch(/<output[^>]*aria-label="Quantidade"[^>]*>2<\/output>/);
  });

  it("409 de outra aba na quantidade volta com a mensagem do cart", async () => {
    mocks.cartPatch.mockResolvedValue(problem(409, { code: "cart.cart.concurrent_update" }));

    const state = await actions.updateQuantityAction(
      null,
      form({ variant_id: VARIANT, quantity: "3" }),
    );

    expect(state).toEqual({
      ok: false,
      message: "Seu carrinho mudou em outra aba. Tente de novo.",
    });
  });

  it("Remover cupom: as classes próprias vencem as do Button ghost (twMerge)", async () => {
    mocks.cartGet.mockResolvedValue(
      ok(
        cartOut({
          items: [item()],
          coupon: { code: "VERAO", valid: true, reason: null, min_order_cents: null },
        }),
      ),
    );

    const button = formWith(formsOf(await renderPage()), "Remover cupom").html.match(
      /<button[^>]*class="([^"]*)"/,
    )?.[1];
    const classes = new Set(button?.split(" "));

    for (const wanted of ["h-8", "px-2", "text-xs", "text-ks-muted", "hover:text-ks-fg"]) {
      expect(classes.has(wanted), wanted).toBe(true);
    }
    for (const lost of ["h-10", "px-4", "text-sm", "text-ks-fg"]) {
      expect(classes.has(lost), lost).toBe(false);
    }
  });

  it("ações de botão do carrinho mostram o erro num role=status", async () => {
    mocks.jar.set(CART_FLASH_COOKIE, { value: "merge_adjusted" });
    mocks.cartGet.mockResolvedValue(
      ok(
        cartOut({
          items: [item(), item({ variant_id: OTHER, unavailable: true, available: 0 })],
          checkout_blocked: true,
          coupon: { code: "VERAO", valid: true, reason: null, min_order_cents: null },
        }),
      ),
    );

    const forms = formsOf(await renderPage());

    for (const marker of ["Entendi", "Limpar indisponíveis", "Remover cupom"]) {
      expect(formWith(forms, marker).html).toContain('role="status"');
    }
  });
});

describe("página /carrinho", () => {
  it("vazio: estado honesto e CTA para todas as peças", async () => {
    mocks.cartGet.mockResolvedValue(ok(cartOut()));

    const html = await renderPage();

    expect(html).toContain("Seu carrinho está vazio.");
    expect(html).toMatch(/<a[^>]*href="\/busca"[^>]*>Ver todas as peças<\/a>/);
    expect(html).not.toContain("Finalizar compra");
  });

  it("visitante sem cookie também vê o vazio, sem chamar o cart", async () => {
    mocks.jar.clear();

    const html = await renderPage();

    expect(html).toContain("Seu carrinho está vazio.");
    expect(mocks.cartGet).not.toHaveBeenCalled();
  });

  it("cart fora do ar lança para cair na página de erro da marca (R22)", async () => {
    mocks.cartGet.mockRejectedValue(new TypeError("fetch failed"));

    await expect(CartPage()).rejects.toThrow(/unavailable/);
  });

  it("com itens: quantidade acessível, preço em mono limão, resumo e checkout desabilitado", async () => {
    mocks.cartGet.mockResolvedValue(
      ok(
        cartOut({
          items: [item()],
          subtotal_cents: 29980,
          total_cents: 29980,
        }),
      ),
    );

    const html = await renderPage();

    expect(html).toContain('aria-label="Diminuir quantidade"');
    expect(html).toContain('aria-label="Aumentar quantidade"');
    expect(html).toMatch(/class="[^"]*font-mono[^"]*text-accent[^"]*"[^>]*>R\$ 299,80/);
    expect(html).toContain("Subtotal");
    expect(html).toContain("Total");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Finalizar compra<\/button>/);
    expect(html).toContain("Checkout chega na próxima versão");
    expect(html).not.toContain("Remova os itens indisponíveis para continuar.");
  });

  it("botão + fica desabilitado no limite do estoque", async () => {
    mocks.cartGet.mockResolvedValue(ok(cartOut({ items: [item({ quantity: 2, available: 2 })] })));

    const html = await renderPage();

    expect(html).toMatch(/<button[^>]*aria-label="Aumentar quantidade"[^>]*disabled=""/);
  });

  it("bloqueado: item indisponível, aviso e botão de limpar", async () => {
    mocks.cartGet.mockResolvedValue(
      ok(
        cartOut({
          items: [
            item(),
            item({
              variant_id: OTHER,
              unavailable: true,
              available: 0,
              notice: {
                code: "unavailable",
                old_price_cents: null,
                new_price_cents: null,
                quantity: null,
              },
            }),
          ],
          subtotal_cents: 29980,
          total_cents: 29980,
          checkout_blocked: true,
        }),
      ),
    );

    const html = await renderPage();

    expect(html).toContain("Remova os itens indisponíveis para continuar.");
    expect(html).toContain("Este item esgotou ou saiu da loja. Remova para continuar.");
    expect(html).toContain("Limpar indisponíveis");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Finalizar compra<\/button>/);
  });

  it("avisos por item com o botão Entendi", async () => {
    mocks.cartGet.mockResolvedValue(
      ok(
        cartOut({
          items: [
            item({
              notice: {
                code: "price_changed",
                old_price_cents: 14990,
                new_price_cents: 12990,
                quantity: null,
              },
            }),
          ],
        }),
      ),
    );

    const html = await renderPage();

    expect(html).toContain("O preço mudou de R$ 149,90 para R$ 129,90.");
    expect(html).toContain("Entendi");
  });

  it("flash do merge aparece com o botão Entendi", async () => {
    mocks.jar.set(CART_FLASH_COOKIE, { value: "merge_adjusted" });
    mocks.cartGet.mockResolvedValue(ok(cartOut({ items: [item()] })));

    const html = await renderPage();

    expect(html).toContain("Alguns itens foram ajustados ao juntar seu carrinho.");
    expect(html).toContain("Entendi");
  });

  it("sem aviso nem flash, sem botão Entendi", async () => {
    mocks.cartGet.mockResolvedValue(ok(cartOut({ items: [item()] })));

    expect(await renderPage()).not.toContain("Entendi");
  });

  it("cupom válido mostra o código e o desconto", async () => {
    mocks.cartGet.mockResolvedValue(
      ok(
        cartOut({
          items: [item()],
          subtotal_cents: 29980,
          discount_cents: 2998,
          total_cents: 26982,
          coupon: { code: "BEMVINDO10", valid: true, reason: null, min_order_cents: null },
        }),
      ),
    );

    const html = await renderPage();

    expect(html).toContain("BEMVINDO10");
    expect(html).toContain("R$ 29,98");
    expect(html).toContain("R$ 269,82");
    expect(html).toContain("Remover cupom");
  });

  it("cupom que deixou de valer mostra o motivo, desconto zero e o botão de remover", async () => {
    mocks.cartGet.mockResolvedValue(
      ok(
        cartOut({
          items: [item()],
          subtotal_cents: 29980,
          total_cents: 29980,
          coupon: {
            code: "BEMVINDO10",
            valid: false,
            reason: "promotions.coupon.min_order_not_met",
            min_order_cents: 50000,
          },
        }),
      ),
    );

    const html = await renderPage();

    expect(html).toContain("BEMVINDO10");
    expect(html).toContain("Pedido mínimo de R$ 500,00 em itens válidos para este cupom.");
    expect(html).toContain("Remover cupom");
  });

  it("sem cupom mostra o formulário", async () => {
    mocks.cartGet.mockResolvedValue(ok(cartOut({ items: [item()] })));

    const html = await renderPage();

    expect(html).toContain('name="code"');
    expect(html).toContain("Aplicar");
  });
});
