import { describe, expect, it } from "vitest";
import { lineVersion, messageForCoupon, messageForNotice } from "../lib/cart-messages";

// NBSP do Intl.NumberFormat (escrito por código: o lint recusa o caractere literal)
const NBSP = String.fromCharCode(0xa0);
const plain = (text: string) => text.replaceAll(NBSP, " ");

describe("messageForNotice", () => {
  it("price_changed mostra o preço antigo e o novo em BRL", () => {
    const text = messageForNotice({
      code: "price_changed",
      old_price_cents: 14990,
      new_price_cents: 12990,
      quantity: null,
    });
    expect(plain(text)).toBe("O preço mudou de R$ 149,90 para R$ 129,90.");
  });

  it("quantity_reduced mostra a nova quantidade", () => {
    const text = messageForNotice({
      code: "quantity_reduced",
      old_price_cents: null,
      new_price_cents: null,
      quantity: 2,
    });
    expect(text).toBe("Ajustamos a quantidade para 2, que é o que temos em estoque.");
  });

  it("unavailable pede para remover", () => {
    const text = messageForNotice({
      code: "unavailable",
      old_price_cents: null,
      new_price_cents: null,
      quantity: null,
    });
    expect(text).toBe("Este item esgotou ou saiu da loja. Remova para continuar.");
  });

  it("aviso sem os dados esperados não inventa número", () => {
    const empty = { old_price_cents: null, new_price_cents: null, quantity: null };
    expect(messageForNotice({ code: "price_changed", ...empty })).toBe("O preço deste item mudou.");
    expect(messageForNotice({ code: "quantity_reduced", ...empty })).toBe(
      "Ajustamos a quantidade ao que temos em estoque.",
    );
  });
});

describe("messageForCoupon", () => {
  it.each([
    ["promotions.coupon.not_found", "Cupom não encontrado."],
    ["promotions.coupon.inactive", "Este cupom não está ativo."],
    ["promotions.coupon.not_started", "Este cupom ainda não começou a valer."],
    ["promotions.coupon.expired", "Este cupom expirou."],
    ["promotions.coupon.no_eligible_items", "Nenhum item do carrinho vale para este cupom."],
    ["promotions.coupon.usage_limit_reached", "Este cupom atingiu o limite de usos."],
    ["promotions.coupon.login_required", "Entre na sua conta para usar este cupom."],
    ["promotions.coupon.customer_limit_reached", "Você já usou este cupom."],
    ["promotions.unavailable", "Não foi possível validar o cupom agora."],
  ])("%s", (reason, message) => {
    expect(messageForCoupon(reason)).toBe(message);
  });

  it("min_order_not_met mostra o mínimo em BRL, contado só nos itens válidos", () => {
    // O cart não expõe as restrições do cupom: a frase vale com e sem restrição.
    expect(plain(messageForCoupon("promotions.coupon.min_order_not_met", 20000))).toBe(
      "Pedido mínimo de R$ 200,00 em itens válidos para este cupom.",
    );
  });

  it("min_order_not_met sem o valor não inventa número", () => {
    expect(messageForCoupon("promotions.coupon.min_order_not_met", null)).toBe(
      "Este cupom pede um valor mínimo de pedido.",
    );
  });

  it("motivo desconhecido ou ausente cai numa mensagem genérica", () => {
    expect(messageForCoupon("promotions.coupon.algo_novo")).toBe("Este cupom não vale agora.");
    expect(messageForCoupon(null)).toBe("Este cupom não vale agora.");
  });
});

describe("lineVersion", () => {
  const line = {
    quantity: 2,
    available: 5,
    unavailable: false,
    unit_price_cents: 14990,
    notice: null,
  };

  it("é estável para a mesma linha", () => {
    expect(lineVersion(line)).toBe(lineVersion({ ...line }));
  });

  it.each([
    { quantity: 3 },
    { available: 2 },
    { unavailable: true },
    { unit_price_cents: 12990 },
    {
      notice: {
        code: "price_changed" as const,
        old_price_cents: 14990,
        new_price_cents: 12990,
        quantity: null,
      },
    },
  ])("muda quando a linha muda (%o), e o erro antigo some", (change) => {
    expect(lineVersion({ ...line, ...change })).not.toBe(lineVersion(line));
  });
});
