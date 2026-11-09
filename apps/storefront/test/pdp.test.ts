import { describe, expect, it } from "vitest";
import { findVariant, imagesForColor, type ProductDetail, sizeStates } from "../lib/pdp";

function image(url: string, color_code: string | null) {
  return {
    url,
    alt: url,
    color_code,
    width: 1200,
    height: 1500,
    credit_author: null,
    credit_source_url: null,
    license: null,
  };
}

function variant(color_code: string, size_code: string, available: boolean, price_cents = 14990) {
  return { sku: `MOL-${color_code}-${size_code}`, color_code, size_code, price_cents, available };
}

const detail: ProductDetail = {
  slug: "moletom-zip",
  name: "Moletom Zip",
  description: null,
  attributes: {},
  category: { slug: "moletons", name: "Moletons" },
  min_price_cents: 14990,
  colors: [
    { code: "PRT", name: "Preto", hex: "#111111" },
    { code: "CNZ", name: "Cinza mescla", hex: "#8C8C88" },
  ],
  sizes: [
    { code: "P", label: "P" },
    { code: "M", label: "M" },
    { code: "G", label: "G" },
    { code: "XG", label: "XG" },
  ],
  variants: [
    variant("PRT", "P", true),
    variant("PRT", "M", true, 15990),
    variant("PRT", "G", false),
    variant("CNZ", "M", true),
    variant("CNZ", "XG", true),
  ],
  images: [
    image("generica-1", null),
    image("cinza-1", "CNZ"),
    image("preto-1", "PRT"),
    image("generica-2", null),
    image("preto-2", "PRT"),
  ],
};

describe("sizeStates", () => {
  it("G sem estoque em PRT fica esgotado e XG inexistente fica ausente, na ordem do detalhe", () => {
    expect(sizeStates(detail, "PRT")).toEqual([
      { code: "P", label: "P", state: "available" },
      { code: "M", label: "M", state: "available" },
      { code: "G", label: "G", state: "sold_out" },
      { code: "XG", label: "XG", state: "absent" },
    ]);
  });

  it("depende da cor", () => {
    expect(sizeStates(detail, "CNZ").map((s) => s.state)).toEqual([
      "absent",
      "available",
      "absent",
      "available",
    ]);
  });

  it("cor desconhecida deixa tudo ausente", () => {
    expect(sizeStates(detail, "AZM").every((s) => s.state === "absent")).toBe(true);
  });
});

describe("imagesForColor", () => {
  it("põe as imagens da cor antes das genéricas, preservando a ordem, e deixa de fora as outras cores", () => {
    expect(imagesForColor(detail.images, "PRT").map((i) => i.url)).toEqual([
      "preto-1",
      "preto-2",
      "generica-1",
      "generica-2",
    ]);
  });

  it("cor sem fotos próprias mostra só as genéricas", () => {
    expect(imagesForColor(detail.images, "AZM").map((i) => i.url)).toEqual([
      "generica-1",
      "generica-2",
    ]);
  });
});

describe("findVariant", () => {
  it("acha a variante pela cor e tamanho", () => {
    expect(findVariant(detail, "PRT", "M")?.sku).toBe("MOL-PRT-M");
  });

  it("devolve undefined quando a combinação não existe", () => {
    expect(findVariant(detail, "CNZ", "G")).toBeUndefined();
    expect(findVariant(detail, "PRT", undefined)).toBeUndefined();
  });
});
