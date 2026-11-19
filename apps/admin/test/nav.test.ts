import { describe, expect, it } from "vitest";
import { isActive, NAV_ITEMS } from "../lib/nav";

describe("NAV_ITEMS", () => {
  it("itens ativos com destino (Cupons chega na fatia 2)", () => {
    const active = NAV_ITEMS.filter((item) => item.href !== undefined).map((item) => item.label);
    expect(active).toEqual(["Visão geral", "Produtos", "Categorias", "Coleções", "Cupons"]);
    expect(NAV_ITEMS.find((item) => item.label === "Cupons")?.href).toBe("/cupons");
  });

  it("itens futuros desabilitados com a fatia em que chegam", () => {
    const disabled = NAV_ITEMS.filter((item) => item.href === undefined).map(
      (item) => `${item.label} (${item.slice ?? ""})`,
    );
    expect(disabled).toEqual([
      "Pedidos (Fatia 3)",
      "Frete (Fatia 3)",
      "Clientes (Fatia 4)",
      "Vitrine (Fatia 4)",
      "Saúde do sistema (Fatia 4)",
      "Auditoria (Fatia 4)",
    ]);
  });
});

describe("isActive", () => {
  it("visão geral só na raiz", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/produtos", "/")).toBe(false);
  });

  it("seções valem para as subpáginas, sem casar prefixo de outra palavra", () => {
    expect(isActive("/produtos", "/produtos")).toBe(true);
    expect(isActive("/produtos/abc", "/produtos")).toBe(true);
    expect(isActive("/produtos-arquivados", "/produtos")).toBe(false);
  });
});
