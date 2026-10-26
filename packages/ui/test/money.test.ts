import { describe, expect, it } from "vitest";
import { formatBRL, installments, pixPrice } from "../src/lib/money";

describe("money", () => {
  it("formata centavos em BRL", () => {
    // Intl usa espaço não separável entre símbolo e valor
    expect(formatBRL(29900).replace(/\u00a0/g, " ")).toBe("R$ 299,00");
  });
  it("calcula parcelas arredondando para cima", () => {
    expect(installments(29900, 3)).toEqual({ count: 3, eachCents: 9967 });
  });
  it("calcula preço no Pix", () => {
    expect(pixPrice(29900, 5)).toBe(28405);
  });
});
