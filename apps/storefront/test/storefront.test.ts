import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", () => ({
  catalog: () => ({ GET: get }),
  revalidate: () => fetch,
}));

const { navCategories, storePolicies } = await import("../lib/storefront");

function timeout(): Promise<never> {
  return Promise.reject(new DOMException("The operation was aborted due to timeout", "TimeoutError"));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("chamadas ao catálogo do layout", () => {
  it("categorias usam timeout de 2 s", async () => {
    get.mockResolvedValue({ data: { items: [] } });

    await navCategories();

    const init = get.mock.calls[0]?.[1] as { signal?: AbortSignal };
    expect(get).toHaveBeenCalledWith("/v1/categories", expect.anything());
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("políticas usam timeout de 2 s", async () => {
    get.mockResolvedValue({ data: undefined });

    await storePolicies();

    const init = get.mock.calls[0]?.[1] as { signal?: AbortSignal };
    expect(get).toHaveBeenCalledWith("/v1/storefront/settings", expect.anything());
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("timeout do catálogo cai nos fallbacks", async () => {
    get.mockImplementation(timeout);

    await expect(navCategories()).resolves.toEqual([]);
    await expect(storePolicies()).resolves.toBeNull();
  });

  it("chamada que nunca termina (sinal ignorado pelo cache do Next) cai no fallback em 2 s", async () => {
    vi.useFakeTimers();
    try {
      get.mockReturnValue(new Promise(() => {}));

      const categories = navCategories();
      const policies = storePolicies();
      await vi.advanceTimersByTimeAsync(2000);

      await expect(categories).resolves.toEqual([]);
      await expect(policies).resolves.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("o sinal é AbortSignal.timeout(2000)", async () => {
    const spy = vi.spyOn(AbortSignal, "timeout");
    get.mockResolvedValue({ data: { items: [] } });

    await navCategories();
    await storePolicies();

    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy).toHaveBeenCalledWith(2000);
    spy.mockRestore();
  });
});

const { apiQuery, listProducts, productDetail, productFacets, storeSettings, allProductSlugs } =
  await import("../lib/storefront");

function reply(status: number, data?: unknown) {
  const response = new Response(null, { status });
  return status < 400 ? { data, response } : { error: { code: "x" }, response };
}

describe("consulta de produtos", () => {
  it("monta a query da API a partir do escopo e dos filtros", () => {
    expect(
      apiQuery(
        { category: "moletons" },
        { size: ["M"], color: ["PRT", "BRC"], priceMin: 10000, sort: "price_asc", q: "zip" },
      ),
    ).toEqual({
      category: "moletons",
      size: ["M"],
      color: ["PRT", "BRC"],
      price_min: 10000,
      sort: "price_asc",
      q: "zip",
    });
    expect(apiQuery({ collection: "drop-01" }, { size: [], color: [], sort: "newest" })).toEqual({
      collection: "drop-01",
      size: [],
      color: [],
      sort: "newest",
    });
  });

  it("listagem passa cursor e limite, com prazo de 2 s", async () => {
    get.mockResolvedValue(reply(200, { items: [], next_cursor: null }));

    const result = await listProducts({}, { size: [], color: [], sort: "newest" }, "abc", 8);

    expect(result).toEqual({ ok: true, data: { items: [], next_cursor: null } });
    const init = get.mock.calls[0]?.[1] as {
      params: { query: Record<string, unknown> };
      signal?: AbortSignal;
    };
    expect(get).toHaveBeenCalledWith("/v1/products", expect.anything());
    expect(init.params.query).toMatchObject({ cursor: "abc", limit: 8, sort: "newest" });
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("422 da API vira filtro inválido, não erro", async () => {
    get.mockResolvedValue(reply(422));
    await expect(listProducts({}, { size: [], color: [], sort: "newest" })).resolves.toEqual({
      ok: false,
      reason: "invalid",
    });
  });

  it("falha ou timeout do catálogo vira indisponível", async () => {
    get.mockResolvedValue(reply(503));
    await expect(listProducts({}, { size: [], color: [], sort: "newest" })).resolves.toEqual({
      ok: false,
      reason: "unavailable",
    });
    get.mockImplementation(timeout);
    await expect(listProducts({}, { size: [], color: [], sort: "newest" })).resolves.toEqual({
      ok: false,
      reason: "unavailable",
    });
  });

  it("facetas com erro devolvem null", async () => {
    get.mockResolvedValue(reply(422));
    await expect(productFacets({}, { size: [], color: [], sort: "newest" })).resolves.toBeNull();
  });
});

describe("detalhe e configurações", () => {
  it("produto inexistente é not_found", async () => {
    get.mockResolvedValue(reply(404));
    await expect(productDetail("nao-existe")).resolves.toEqual({ ok: false, reason: "not_found" });
    expect(get).toHaveBeenCalledWith("/v1/products/{slug}", expect.objectContaining({
      params: { path: { slug: "nao-existe" } },
    }));
  });

  it("slug fora do padrão nem chega na API", async () => {
    await expect(productDetail("../admin")).resolves.toEqual({ ok: false, reason: "not_found" });
    expect(get).not.toHaveBeenCalled();
  });

  it("configurações ausentes (404) viram null", async () => {
    get.mockResolvedValue(reply(404));
    await expect(storeSettings()).resolves.toBeNull();
  });

  it("slugs do sitemap percorrem todas as páginas da API", async () => {
    get
      .mockResolvedValueOnce(reply(200, { items: [{ slug: "a" }, { slug: "b" }], next_cursor: "c1" }))
      .mockResolvedValueOnce(reply(200, { items: [{ slug: "c" }], next_cursor: null }));

    await expect(allProductSlugs()).resolves.toEqual(["a", "b", "c"]);
    const second = get.mock.calls[1]?.[1] as { params: { query: Record<string, unknown> } };
    expect(second.params.query).toMatchObject({ cursor: "c1", limit: 100 });
  });
});

const { categoryBySlug } = await import("../lib/storefront");

describe("fix round 1: indisponível não é inexistente", () => {
  it("categoria existente vem da lista carregada", async () => {
    get.mockResolvedValue(
      reply(200, { items: [{ slug: "moletons", name: "Moletons", parent_slug: null, position: 1 }] }),
    );
    await expect(categoryBySlug("moletons")).resolves.toEqual({
      ok: true,
      data: { slug: "moletons", name: "Moletons", parent_slug: null, position: 1 },
    });
  });

  it("not_found só quando a lista carregou e o slug não está nela", async () => {
    get.mockResolvedValue(reply(200, { items: [] }));
    await expect(categoryBySlug("nao-existe")).resolves.toEqual({ ok: false, reason: "not_found" });
  });

  it("catálogo fora do ar (5xx ou timeout) é unavailable, não not_found", async () => {
    get.mockResolvedValue(reply(503));
    await expect(categoryBySlug("moletons")).resolves.toEqual({ ok: false, reason: "unavailable" });
    get.mockImplementation(timeout);
    await expect(categoryBySlug("moletons")).resolves.toEqual({ ok: false, reason: "unavailable" });
  });

  it("slugs do sitemap: erro no meio da paginação lança em vez de devolver lista parcial", async () => {
    get
      .mockResolvedValueOnce(reply(200, { items: [{ slug: "a" }], next_cursor: "c1" }))
      .mockResolvedValueOnce(reply(503));
    await expect(allProductSlugs()).rejects.toThrow();
  });

  it("slugs do sitemap: erro já na primeira página também lança", async () => {
    get.mockImplementation(timeout);
    await expect(allProductSlugs()).rejects.toThrow();
  });
});
