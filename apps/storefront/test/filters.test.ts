import { describe, expect, it } from "vitest";
import { type CatalogFilters, parseFilters, toSearchParams } from "../lib/filters";

function roundTrip(f: CatalogFilters): CatalogFilters {
  const sp: Record<string, string | string[]> = {};
  for (const [key, value] of toSearchParams(f)) {
    const current = sp[key];
    sp[key] = current === undefined ? value : [...(Array.isArray(current) ? current : [current]), value];
  }
  return parseFilters(sp);
}

describe("parseFilters", () => {
  it("lê tamanhos, cor e preço em reais; ordem inválida vira o padrão", () => {
    expect(parseFilters({ tamanho: ["M", "G"], cor: "PRT", preco_min: "100", ordem: "xyz" })).toEqual({
      size: ["M", "G"],
      color: ["PRT"],
      priceMin: 10000,
      sort: "newest",
    });
  });

  it("sem parâmetros: listagem vazia ordenada por novidades", () => {
    expect(parseFilters({})).toEqual({ size: [], color: [], sort: "newest" });
  });

  it("com busca o padrão é relevância e o texto é aparado", () => {
    expect(parseFilters({ q: "  moletom preto " })).toEqual({
      size: [],
      color: [],
      sort: "relevance",
      q: "moletom preto",
    });
  });

  it("busca vazia ou só com espaços equivale a sem busca", () => {
    expect(parseFilters({ q: "   " }).q).toBeUndefined();
    expect(parseFilters({ q: "" }).sort).toBe("newest");
  });

  it("aceita uma ordem válida", () => {
    expect(parseFilters({ ordem: "price_desc" }).sort).toBe("price_desc");
  });

  it("descarta códigos fora do padrão da API e repetidos", () => {
    expect(
      parseFilters({ tamanho: ["m", "GG", "XXXXX", "GG", "G'"], cor: ["PRT", "<b>", ""] }),
    ).toMatchObject({ size: ["GG"], color: ["PRT"] });
  });

  it("limita a 20 códigos por dimensão", () => {
    const many = Array.from({ length: 30 }, (_, i) => String.fromCharCode(65 + (i % 26)) + (i >= 26 ? "Z" : ""));
    expect(parseFilters({ tamanho: many }).size).toHaveLength(20);
  });

  it("ignora preço inválido, negativo, fracionado ou acima do limite", () => {
    for (const value of ["abc", "-1", "10.5", "1e3", "", "99999999"]) {
      const f = parseFilters({ preco_min: value, preco_max: value });
      expect(f.priceMin, value).toBeUndefined();
      expect(f.priceMax, value).toBeUndefined();
    }
    expect(parseFilters({ preco_max: "0" }).priceMax).toBe(0);
  });

  it("usa o primeiro valor quando um parâmetro único vem repetido", () => {
    expect(parseFilters({ preco_max: ["250", "300"], ordem: ["price_asc", "newest"] })).toMatchObject({
      priceMax: 25000,
      sort: "price_asc",
    });
  });

  it("troca caracteres de controle da busca por espaço", () => {
    expect(parseFilters({ q: "moletom\u0000\npreto" }).q).toBe("moletom  preto");
  });
});

describe("toSearchParams", () => {
  it("usa os nomes da URL e preço em reais", () => {
    const sp = toSearchParams({
      size: ["M", "G"],
      color: ["PRT"],
      priceMin: 10000,
      priceMax: 25000,
      sort: "price_asc",
      q: "moletom",
    });
    expect(sp.toString()).toBe(
      "q=moletom&tamanho=M&tamanho=G&cor=PRT&preco_min=100&preco_max=250&ordem=price_asc",
    );
  });

  it("omite a ordem quando é o padrão", () => {
    expect(toSearchParams({ size: [], color: [], sort: "newest" }).toString()).toBe("");
    expect(toSearchParams({ size: [], color: [], sort: "relevance", q: "x" }).toString()).toBe("q=x");
  });

  it("faz o caminho de ida e volta com parseFilters", () => {
    const inputs: Record<string, string | string[]>[] = [
      { tamanho: ["M", "G"], cor: "PRT", preco_min: "100", ordem: "xyz" },
      { q: "camiseta", ordem: "newest", preco_max: "0" },
      { cor: ["PRT", "BRC"], ordem: "price_desc", preco_min: "50", preco_max: "300" },
      {},
    ];
    for (const input of inputs) {
      const f = parseFilters(input);
      expect(roundTrip(f)).toEqual(f);
    }
  });
});
