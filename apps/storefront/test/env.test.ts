import { afterEach, describe, expect, it, vi } from "vitest";
import { cartApiUrl } from "../lib/env";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("cartApiUrl (S13)", () => {
  it("usa CART_API_URL (rede interna) sem barra final", () => {
    vi.stubEnv("CART_API_URL", "http://cart:8000/");
    expect(cartApiUrl()).toBe("http://cart:8000");
  });

  it("sem CART_API_URL cai no gateway em API_URL/cart", () => {
    vi.stubEnv("CART_API_URL", "");
    vi.stubEnv("API_URL", "http://gw.local");
    expect(cartApiUrl()).toBe("http://gw.local/cart");
  });
});
