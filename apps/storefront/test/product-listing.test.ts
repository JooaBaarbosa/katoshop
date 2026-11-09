import { beforeEach, describe, expect, it, vi } from "vitest";

const listProducts = vi.hoisted(() => vi.fn());
const productFacets = vi.hoisted(() => vi.fn());

vi.mock("../lib/storefront", () => ({ listProducts, productFacets }));

const { ProductListing } = await import("../components/product-listing");

const props = {
  scope: { category: "camisetas" },
  filters: { size: [], color: [], sort: "newest" as const },
  action: "/c/camisetas",
  header: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  productFacets.mockResolvedValue(null);
});

describe("ProductListing com falha do catálogo (R22)", () => {
  it("catálogo indisponível lança, para cair no error.tsx da marca", async () => {
    listProducts.mockResolvedValue({ ok: false, reason: "unavailable" });
    await expect(ProductListing(props)).rejects.toThrow(/unavailable/);
  });

  it("filtro inválido (422) continua como aviso inline, sem lançar", async () => {
    listProducts.mockResolvedValue({ ok: false, reason: "invalid" });
    await expect(ProductListing(props)).resolves.toBeTruthy();
  });
});
