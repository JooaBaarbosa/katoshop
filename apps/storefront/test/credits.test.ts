import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ catalog: () => ({ GET: get }), revalidate: () => fetch }));

const { photoCredits } = await import("../lib/storefront");
const { safeHttpUrl } = await import("../lib/credits");

beforeEach(() => vi.clearAllMocks());

describe("photoCredits", () => {
  it("devolve a lista da API, com prazo de 2 s", async () => {
    const items = [
      {
        product_name: "Camiseta",
        image_url: "http://x/y.webp",
        credit_author: "Ana",
        credit_source_url: "https://example.com/a",
        license: "CC0",
      },
    ];
    get.mockResolvedValue({ data: { items }, response: new Response(null, { status: 200 }) });

    await expect(photoCredits()).resolves.toEqual({ ok: true, data: items });
    const init = get.mock.calls[0]?.[1] as { signal?: AbortSignal };
    expect(get).toHaveBeenCalledWith("/v1/credits", expect.anything());
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("falha do catálogo é indisponível, não lista vazia", async () => {
    get.mockResolvedValue({ error: {}, response: new Response(null, { status: 503 }) });
    await expect(photoCredits()).resolves.toEqual({ ok: false, reason: "unavailable" });
    get.mockRejectedValue(new Error("boom"));
    await expect(photoCredits()).resolves.toEqual({ ok: false, reason: "unavailable" });
  });
});

describe("safeHttpUrl", () => {
  it("aceita apenas http e https", () => {
    expect(safeHttpUrl("https://unsplash.com/photos/abc")).toBe("https://unsplash.com/photos/abc");
    expect(safeHttpUrl("http://example.com")).toBe("http://example.com/");
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("data:text/html,x")).toBeNull();
    expect(safeHttpUrl("//evil.com")).toBeNull();
    expect(safeHttpUrl("não é url")).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
  });
});
