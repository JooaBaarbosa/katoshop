import { describe, expect, it } from "vitest";
import {
  formatAttributes,
  formatCentsInput,
  parseAttributes,
  parseDelta,
  parsePriceCents,
  publishBlockers,
  sortVariants,
} from "../lib/catalog-input";

describe("parsePriceCents", () => {
  it.each([
    ["129,90", 12990],
    ["129.90", 12990],
    ["129", 12900],
    ["R$ 1.299,90", 129990],
    [" 0,5 ", 50],
    ["0", 0],
  ])("%s vira %s centavos", (input, cents) => {
    expect(parsePriceCents(input)).toBe(cents);
  });

  it.each(["", "abc", "-10", "12,345", "1,2,3"])("%s é inválido", (input) => {
    expect(parsePriceCents(input)).toBeNull();
  });
});

describe("formatCentsInput", () => {
  it("formata para edição sem símbolo", () => {
    expect(formatCentsInput(12990)).toBe("129,90");
    expect(formatCentsInput(5)).toBe("0,05");
  });
});

describe("atributos", () => {
  it("lê uma linha por atributo no formato chave: valor", () => {
    expect(parseAttributes("Composição: 100% algodão\n\n Modelagem :  ampla \nsem dois pontos")).toEqual(
      { Composição: "100% algodão", Modelagem: "ampla" },
    );
  });

  it("valor pode conter dois pontos", () => {
    expect(parseAttributes("Cuidados: lavar a 30: avesso")).toEqual({
      Cuidados: "lavar a 30: avesso",
    });
  });

  it("formata texto e número, ignorando estruturas", () => {
    expect(formatAttributes({ composicao: "algodão", gramatura: 240, extra: { a: 1 } })).toBe(
      "composicao: algodão\ngramatura: 240",
    );
  });
});

describe("parseDelta", () => {
  it.each([
    ["5", 5],
    ["-3", -3],
    ["+2", 2],
  ])("%s vira %s", (input, value) => {
    expect(parseDelta(input)).toBe(value);
  });

  it.each(["0", "", "1.5", "abc", "2000000"])("%s é inválido", (input) => {
    expect(parseDelta(input)).toBeNull();
  });
});

const variant = (over: Partial<{ active: boolean; effective_price_cents: number; color_code: string; size_code: string }>) => ({
  active: true,
  effective_price_cents: 100,
  color_code: "PRT",
  size_code: "M",
  ...over,
});

describe("publishBlockers", () => {
  it("espelha as regras do catálogo", () => {
    expect(publishBlockers({ variants: [], images: [] })).toEqual(["no_active_variant", "no_image"]);
    expect(
      publishBlockers({ variants: [variant({ effective_price_cents: 0 })], images: [{}] }),
    ).toEqual(["no_price"]);
    expect(publishBlockers({ variants: [variant({ active: false })], images: [{}] })).toEqual([
      "no_active_variant",
    ]);
    expect(publishBlockers({ variants: [variant({})], images: [{}] })).toEqual([]);
  });
});

describe("sortVariants", () => {
  it("ordena pela cor de referência e pelo tamanho PP..XGG", () => {
    const sorted = sortVariants([
      variant({ color_code: "BRC", size_code: "G" }),
      variant({ color_code: "PRT", size_code: "XGG" }),
      variant({ color_code: "PRT", size_code: "PP" }),
      variant({ color_code: "BRC", size_code: "P" }),
    ]);
    expect(sorted.map((v) => `${v.color_code}-${v.size_code}`)).toEqual([
      "PRT-PP",
      "PRT-XGG",
      "BRC-P",
      "BRC-G",
    ]);
  });
});
