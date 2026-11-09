import { describe, expect, it } from "vitest";
import { safeNext } from "../lib/safe-next";

describe("safeNext", () => {
  it("sem destino válido o padrão do admin é a visão geral", () => {
    expect(safeNext(null)).toBe("/");
    expect(safeNext("//evil.example")).toBe("/");
  });

  it("caminho interno passa", () => {
    expect(safeNext("/produtos?status=draft")).toBe("/produtos?status=draft");
  });
});
