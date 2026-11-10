import { ApiProblem } from "@katoshop/api-client";
import { describe, expect, it } from "vitest";
import { blockerMessages, messageFor, problemMessage } from "../lib/problem-messages";

describe("messageFor", () => {
  it("conflito de versão do produto pede para recarregar", () => {
    expect(messageFor("catalog.product.version_conflict")).toContain("alterado por outra pessoa");
    expect(messageFor("catalog.product.version_conflict")).toBe(
      "Este produto foi alterado por outra pessoa. Recarregue para ver a versão atual.",
    );
  });

  it.each([
    ["catalog.product.slug_taken", "Já existe um produto com este endereço."],
    ["catalog.stock.would_go_negative", "O estoque não pode ficar negativo."],
    ["catalog.image.too_large", "A imagem passa de 8 MB."],
    ["catalog.image.unsupported_type", "Envie JPG, PNG ou WebP."],
    ["catalog.category.in_use", "Há produtos nesta categoria."],
  ])("%s tem o texto exato do brief", (code, text) => {
    expect(messageFor(code)).toBe(text);
  });

  it.each(["no_active_variant", "no_image", "no_price"])("blocker %s tem texto em pt-BR", (code) => {
    const text = messageFor(code);
    expect(text).not.toContain("Algo deu errado");
    expect(text.length).toBeGreaterThan(10);
  });

  it("código desconhecido cai no fallback com o traceId", () => {
    expect(messageFor("catalog.nada.disso", "abc123")).toBe(
      "Algo deu errado. Código para suporte: abc123",
    );
  });

  it("sem traceId o fallback não mostra código vazio", () => {
    expect(messageFor("catalog.nada.disso")).not.toContain("undefined");
    expect(messageFor("catalog.nada.disso")).toContain("Algo deu errado");
  });

  it("nenhuma mensagem usa travessão", () => {
    const codes = [
      "catalog.product.version_conflict",
      "catalog.category.parent_cycle",
      "no_active_variant",
      "no_image",
      "no_price",
      "x",
    ];
    for (const code of codes) expect(messageFor(code, "t")).not.toMatch(/[–—]/);
  });
});

describe("problemMessage", () => {
  it("usa o código e o traceId do ApiProblem", () => {
    const problem = new ApiProblem({
      status: 500,
      code: "internal.error",
      message: "Erro interno",
      traceId: "t-1",
    });
    expect(problemMessage(problem)).toBe("Algo deu errado. Código para suporte: t-1");
  });

  it("limite de requisições (429) tem mensagem própria", () => {
    const problem = new ApiProblem({ status: 429, code: "http.429", message: "Too Many" });
    expect(problemMessage(problem)).toContain("Aguarde");
  });

  it("erro que não é da API vira mensagem genérica", () => {
    expect(problemMessage(new TypeError("fetch failed"))).toContain("Algo deu errado");
  });
});

describe("blockerMessages", () => {
  it("lê os blockers de errors.product do 422 not_publishable", () => {
    const problem = new ApiProblem({
      status: 422,
      code: "catalog.product.not_publishable",
      message: "Produto não publicável",
      errors: { product: ["no_image", "no_price"] },
    });
    expect(blockerMessages(problem)).toEqual([messageFor("no_image"), messageFor("no_price")]);
  });
});
