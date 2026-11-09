import { beforeEach, describe, expect, it, vi } from "vitest";

const listProducts = vi.hoisted(() => vi.fn());

vi.mock("../lib/storefront", () => ({ listProducts }));

const { loadMoreProducts } = await import("../app/(shop)/catalog-actions");

const page = { items: [{ slug: "a" }], next_cursor: null };

beforeEach(() => {
  vi.clearAllMocks();
  listProducts.mockResolvedValue({ ok: true, data: page });
});

describe("loadMoreProducts", () => {
  it("revalida escopo e filtros antes de chamar a API", async () => {
    await expect(
      loadMoreProducts({ category: "moletons" }, "tamanho=M&tamanho=x&cor=PRT&preco_min=100", "c1"),
    ).resolves.toEqual(page);
    expect(listProducts).toHaveBeenCalledWith(
      { category: "moletons" },
      { size: ["M"], color: ["PRT"], priceMin: 10000, sort: "newest" },
      "c1",
    );
  });

  it("descarta escopo fora do padrão de slug", async () => {
    await loadMoreProducts({ category: "../x", collection: "Drop" }, "", "c1");
    expect(listProducts).toHaveBeenCalledWith({}, expect.anything(), "c1");
  });

  it("cursor vazio ou longo demais não chama a API", async () => {
    await expect(loadMoreProducts({}, "", "")).resolves.toBeNull();
    await expect(loadMoreProducts({}, "", "x".repeat(2000))).resolves.toBeNull();
    expect(listProducts).not.toHaveBeenCalled();
  });

  it("erro da API (cursor adulterado = 422) devolve null", async () => {
    listProducts.mockResolvedValue({ ok: false, reason: "invalid" });
    await expect(loadMoreProducts({}, "", "adulterado")).resolves.toBeNull();
  });
});
