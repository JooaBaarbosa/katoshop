import { describe, expect, it } from "vitest";
import { move } from "../components/reorder-list";

describe("move", () => {
  it("leva o primeiro para o fim", () => {
    expect(move(["a", "b", "c"], 0, 2)).toEqual(["b", "c", "a"]);
  });

  it("leva o último para o início", () => {
    expect(move(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
  });

  it("troca vizinhos (botões Mover para cima e Mover para baixo)", () => {
    expect(move(["a", "b", "c"], 1, 0)).toEqual(["b", "a", "c"]);
    expect(move(["a", "b", "c"], 1, 2)).toEqual(["a", "c", "b"]);
  });

  it("não altera a lista original", () => {
    const items = ["a", "b", "c"];
    move(items, 0, 2);
    expect(items).toEqual(["a", "b", "c"]);
  });

  it.each([
    [-1, 1],
    [0, 3],
    [3, 0],
    [1, -1],
    [0.5, 1],
  ])("índice fora do intervalo (%s, %s) devolve cópia inalterada", (from, to) => {
    const items = ["a", "b", "c"];
    const result = move(items, from, to);
    expect(result).toEqual(["a", "b", "c"]);
    expect(result).not.toBe(items);
  });

  it("mesmo índice devolve cópia", () => {
    const items = ["a", "b"];
    const result = move(items, 1, 1);
    expect(result).toEqual(items);
    expect(result).not.toBe(items);
  });
});
