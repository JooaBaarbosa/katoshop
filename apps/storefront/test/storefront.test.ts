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
