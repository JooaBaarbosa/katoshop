import { describe, expect, it } from "vitest";
import {
  couponConditions,
  couponValueLabel,
  flashMessage,
  normalizeCouponCode,
  onlyKnown,
  parseCouponForm,
  parseReaisCents,
  saoPauloLocalToUtc,
  utcToSaoPauloLocal,
} from "../lib/coupons";

function form(fields: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (Array.isArray(value)) for (const item of value) data.append(key, item);
    else data.set(key, value);
  }
  return data;
}

const BASE = { code: "BEMVINDO10", kind: "percent", value: "10" };

function errorsOf(fields: Record<string, string | string[]>): Record<string, string> {
  const result = parseCouponForm(form({ ...BASE, ...fields }));
  if (result.ok) throw new Error("esperava erro de validação");
  return result.fieldErrors;
}

function bodyOf(fields: Record<string, string | string[]>) {
  const result = parseCouponForm(form({ ...BASE, ...fields }));
  if (!result.ok) throw new Error(`esperava sucesso: ${JSON.stringify(result.fieldErrors)}`);
  return result.body;
}

describe("normalizeCouponCode", () => {
  it("apara e põe em maiúsculas como o servidor", () => {
    expect(normalizeCouponCode(" bemvindo10 ")).toBe("BEMVINDO10");
    expect(normalizeCouponCode("frete-gratis")).toBe("FRETE-GRATIS");
  });

  it.each(["ab", "a".repeat(33), "PROMO 10", "PROMO_10", "PROMOÇÃO", "ﬀAB"])(
    "recusa %s",
    (raw) => {
      expect(normalizeCouponCode(raw)).toBeNull();
    },
  );
});

describe("parseReaisCents", () => {
  it.each([
    ["10", 1000],
    ["10,50", 1050],
    ["10.50", 1050],
    ["10,5", 1050],
    ["0,01", 1],
    ["R$ 25,90", 2590],
    ["100000,00", 10_000_000],
  ])("%s vira %i centavos sem erro de ponto flutuante", (text, cents) => {
    expect(parseReaisCents(text)).toBe(cents);
  });

  it("0,29 e 4,35 não sofrem arredondamento de float", () => {
    expect(parseReaisCents("0,29")).toBe(29);
    expect(parseReaisCents("4,35")).toBe(435);
    expect(parseReaisCents("1,15")).toBe(115);
  });

  it.each(["", "-10", "10,505", "abc", "0", "0,00", "100000,01", "1.000,00", "10,"])(
    "recusa %s",
    (text) => {
      expect(parseReaisCents(text)).toBeNull();
    },
  );
});

describe("fuso America/Sao_Paulo", () => {
  it("datetime-local vira UTC pela regra do fuso (hoje UTC-3)", () => {
    expect(saoPauloLocalToUtc("2026-12-01T10:30")).toBe("2026-12-01T13:30:00.000Z");
    expect(saoPauloLocalToUtc("2026-12-31T23:59")).toBe("2027-01-01T02:59:00.000Z");
  });

  it("usa o horário de verão quando o fuso o tinha (2018: UTC-2)", () => {
    expect(saoPauloLocalToUtc("2018-01-15T10:00")).toBe("2018-01-15T12:00:00.000Z");
  });

  it("aceita segundos e recusa datas impossíveis ou mal formadas", () => {
    expect(saoPauloLocalToUtc("2026-12-01T10:30:15")).toBe("2026-12-01T13:30:15.000Z");
    expect(saoPauloLocalToUtc("2026-02-30T10:00")).toBeNull();
    expect(saoPauloLocalToUtc("2026-12-01")).toBeNull();
    expect(saoPauloLocalToUtc("amanhã")).toBeNull();
  });

  it("UTC volta para o valor do datetime-local em São Paulo", () => {
    expect(utcToSaoPauloLocal("2026-12-01T13:30:00Z")).toBe("2026-12-01T10:30");
    expect(utcToSaoPauloLocal("2027-01-01T02:59:00+00:00")).toBe("2026-12-31T23:59");
    expect(utcToSaoPauloLocal(null)).toBe("");
  });
});

describe("parseCouponForm", () => {
  it("monta o corpo completo com valores convertidos", () => {
    const body = bodyOf({
      code: " verao-26 ",
      description: "  Verão  ",
      kind: "fixed",
      value: "15,90",
      min_order: "199,90",
      starts_at: "2026-12-01T00:00",
      ends_at: "2027-03-01T00:00",
      category_slugs: ["camisetas", "moletons", "camisetas"],
      collection_slugs: ["verao"],
      max_uses_total: "100",
      max_uses_per_customer: "1",
      active: "on",
    });
    expect(body).toEqual({
      code: "VERAO-26",
      description: "Verão",
      kind: "fixed",
      value: 1590,
      min_order_cents: 19990,
      starts_at: "2026-12-01T03:00:00.000Z",
      ends_at: "2027-03-01T03:00:00.000Z",
      category_slugs: ["camisetas", "moletons"],
      collection_slugs: ["verao"],
      max_uses_total: 100,
      max_uses_per_customer: 1,
      active: true,
    });
  });

  it("opcionais vazios viram null, listas vazias e ativo desmarcado", () => {
    expect(bodyOf({})).toEqual({
      code: "BEMVINDO10",
      description: "",
      kind: "percent",
      value: 10,
      min_order_cents: null,
      starts_at: null,
      ends_at: null,
      category_slugs: [],
      collection_slugs: [],
      max_uses_total: null,
      max_uses_per_customer: null,
      active: false,
    });
  });

  it("código: fora do padrão", () => {
    expect(errorsOf({ code: "a b" })).toEqual({
      code: "Use de 3 a 32 caracteres: letras sem acento, números e hífen.",
    });
  });

  it("tipo: obrigatório e da lista", () => {
    expect(errorsOf({ kind: "" })).toHaveProperty("kind", "Escolha o tipo de desconto.");
    expect(errorsOf({ kind: "brinde" })).toHaveProperty("kind", "Escolha o tipo de desconto.");
  });

  it("valor percentual: inteiro de 1 a 90", () => {
    const message = "Informe um percentual inteiro de 1 a 90.";
    for (const value of ["0", "91", "10,5", "", "-5"]) {
      expect(errorsOf({ value })).toEqual({ value: message });
    }
    expect(bodyOf({ value: "90" }).value).toBe(90);
    expect(bodyOf({ value: "1" }).value).toBe(1);
  });

  it("valor fixo: reais convertidos para centavos, positivo e com no máximo 2 decimais", () => {
    expect(bodyOf({ kind: "fixed", value: "10" }).value).toBe(1000);
    expect(bodyOf({ kind: "fixed", value: "10.50" }).value).toBe(1050);
    expect(errorsOf({ kind: "fixed", value: "-1" })).toEqual({
      value: "Informe um valor em reais maior que zero, como 10,50, até R$ 100.000,00.",
    });
    expect(errorsOf({ kind: "fixed", value: "1,999" })).toHaveProperty("value");
  });

  it("pedido mínimo: reais opcional", () => {
    expect(bodyOf({ min_order: "99" }).min_order_cents).toBe(9900);
    expect(errorsOf({ min_order: "0" })).toEqual({
      min_order: "Informe um valor em reais maior que zero, como 99,90, ou deixe vazio.",
    });
  });

  it("início e fim: data inválida", () => {
    expect(errorsOf({ starts_at: "2026-13-01T10:00" })).toEqual({
      starts_at: "Informe uma data e hora válidas.",
    });
    expect(errorsOf({ ends_at: "x" })).toEqual({ ends_at: "Informe uma data e hora válidas." });
  });

  it("fim depois do início", () => {
    const message = "O fim deve ser depois do início.";
    expect(errorsOf({ starts_at: "2026-12-02T10:00", ends_at: "2026-12-01T10:00" })).toEqual({
      ends_at: message,
    });
    expect(errorsOf({ starts_at: "2026-12-01T10:00", ends_at: "2026-12-01T10:00" })).toEqual({
      ends_at: message,
    });
    expect(bodyOf({ ends_at: "2026-12-01T10:00" }).ends_at).toBe("2026-12-01T13:00:00.000Z");
  });

  it("limites: inteiros a partir de 1", () => {
    const message = "Use um número inteiro a partir de 1, ou deixe vazio.";
    expect(errorsOf({ max_uses_total: "0" })).toEqual({ max_uses_total: message });
    expect(errorsOf({ max_uses_per_customer: "1,5" })).toEqual({ max_uses_per_customer: message });
    expect(errorsOf({ max_uses_total: "3000000000" })).toEqual({ max_uses_total: message });
  });

  it("descrição: até 500 caracteres", () => {
    expect(errorsOf({ description: "a".repeat(501) })).toEqual({
      description: "A descrição aceita no máximo 500 caracteres.",
    });
  });

  it("categorias e coleções: deduplicadas e só as carregadas do catálogo", () => {
    const result = parseCouponForm(
      form({
        ...BASE,
        category_slugs: ["camisetas", "inventada", "camisetas"],
        collection_slugs: ["verao", "x"],
      }),
      { categories: ["camisetas", "moletons"], collections: ["verao"] },
    );
    expect(result).toMatchObject({
      ok: true,
      body: { category_slugs: ["camisetas"], collection_slugs: ["verao"] },
    });
  });

  it("modo edição: não lê nem envia código e ativo", () => {
    const result = parseCouponForm(form({ kind: "percent", value: "5", code: "OUTRO" }), {
      mode: "update",
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.body).not.toHaveProperty("code");
    expect(result.body).not.toHaveProperty("active");
    expect(result.body).toMatchObject({ kind: "percent", value: 5 });
  });

  it("junta os erros de vários campos", () => {
    expect(Object.keys(errorsOf({ code: "", value: "0", max_uses_total: "x" })).sort()).toEqual([
      "code",
      "max_uses_total",
      "value",
    ]);
  });
});

describe("onlyKnown", () => {
  it("mantém a ordem, remove repetidos e desconhecidos", () => {
    expect(onlyKnown(["b", "a", "b", "z"], ["a", "b"])).toEqual(["b", "a"]);
  });
});

describe("exibição", () => {
  it("valor do cupom", () => {
    expect(couponValueLabel({ kind: "percent", value: 15 })).toBe("15%");
    expect(couponValueLabel({ kind: "fixed", value: 1050 })).toMatch(/^R\$\s10,50$/);
  });

  it("condições", () => {
    expect(
      couponConditions({
        min_order_cents: null,
        category_slugs: [],
        collection_slugs: [],
        max_uses_total: null,
        max_uses_per_customer: null,
      }),
    ).toEqual(["Loja toda"]);
    const list = couponConditions({
      min_order_cents: 9990,
      category_slugs: ["camisetas"],
      collection_slugs: ["verao", "basicos"],
      max_uses_total: 100,
      max_uses_per_customer: 1,
    });
    expect(list).toHaveLength(5);
    expect(list[1]).toBe("Categorias: camisetas");
    expect(list[2]).toBe("Coleções: verao, basicos");
    expect(list[3]).toBe("Até 100 usos no total");
    expect(list[4]).toBe("1 uso por cliente");
  });

  it("aviso depois do redirect só aceita chaves conhecidas", () => {
    expect(flashMessage("criado")).toBe("Cupom criado.");
    expect(flashMessage("salvo")).toBe("Alterações salvas.");
    expect(flashMessage("excluido")).toBe("Cupom excluído.");
    expect(flashMessage("<script>")).toBeNull();
    expect(flashMessage(undefined)).toBeNull();
  });
});
