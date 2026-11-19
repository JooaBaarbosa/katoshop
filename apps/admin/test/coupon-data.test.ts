import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  promotions: vi.fn(),
  get: vi.fn(),
  withAuth: vi.fn(),
}));

vi.mock("../lib/api", () => ({ identity: vi.fn(), promotions: mocks.promotions }));
vi.mock("../lib/session", () => ({ session: { withAuth: mocks.withAuth } }));

const { loadCouponList } = await import("../lib/coupon-data");

function ok<T>(data: T) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}

function problem(status: number, body: Record<string, unknown>) {
  return { data: undefined, error: body, response: new Response(null, { status }) };
}

const FIRST_PAGE = { items: [{ id: "c1" }], next_cursor: "n1" };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.promotions.mockReturnValue({ GET: mocks.get });
  mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
});

describe("loadCouponList", () => {
  it("repassa filtros, cursor e limite", async () => {
    mocks.get.mockResolvedValue(ok(FIRST_PAGE));

    const result = await loadCouponList({ q: "bem", active: true, cursor: "c" });

    expect(result).toEqual({ page: FIRST_PAGE, notice: null });
    expect(mocks.get).toHaveBeenCalledWith("/v1/admin/coupons", {
      params: { query: { q: "bem", active: true, cursor: "c", limit: 24 } },
    });
  });

  it("cursor adulterado (422 invalid_cursor) cai na primeira página com aviso", async () => {
    mocks.get
      .mockResolvedValueOnce(problem(422, { code: "promotions.pagination.invalid_cursor" }))
      .mockResolvedValueOnce(ok(FIRST_PAGE));

    const result = await loadCouponList({ q: "bem", cursor: "adulterado" });

    expect(result).toEqual({
      page: FIRST_PAGE,
      notice: "A página pedida não existe mais. Mostrando o início da lista.",
    });
    expect(mocks.get).toHaveBeenLastCalledWith("/v1/admin/coupons", {
      params: { query: { q: "bem", limit: 24 } },
    });
  });

  it("outros erros sobem para a página de erro", async () => {
    mocks.get.mockResolvedValue(problem(500, { code: "internal.error" }));

    await expect(loadCouponList({ cursor: "c" })).rejects.toMatchObject({ status: 500 });
    expect(mocks.get).toHaveBeenCalledTimes(1);
  });
});
