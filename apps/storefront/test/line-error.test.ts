import { describe, expect, it } from "vitest";
import { NO_LINE_ERROR, trackLineError, visibleLineError } from "../lib/line-error";

const stock = { ok: false, message: "Só temos 2 unidades desse tamanho.", max: 2 };
const concurrent = { ok: false, message: "Seu carrinho mudou em outra aba. Tente de novo." };

describe("trackLineError", () => {
  it("o erro aparece na resposta que o traz, mesmo com a linha já atualizada pelo refresh", () => {
    // enviado com a versão "2:5", o refresh trouxe available 2: a linha chega como "2:2"
    const tracked = trackLineError(NO_LINE_ERROR, stock, "2:2");

    expect(visibleLineError(tracked)).toBe("Só temos 2 unidades desse tamanho.");
  });

  it("409 de outra aba mostra a mensagem", () => {
    expect(visibleLineError(trackLineError(NO_LINE_ERROR, concurrent, "3:5"))).toBe(
      "Seu carrinho mudou em outra aba. Tente de novo.",
    );
  });

  it("render seguinte sem mudança mantém o erro (e devolve o mesmo objeto)", () => {
    const tracked = trackLineError(NO_LINE_ERROR, stock, "2:2");

    expect(trackLineError(tracked, stock, "2:2")).toBe(tracked);
  });

  it("some depois de uma mudança posterior na linha e não volta se a versão retornar", () => {
    let tracked = trackLineError(NO_LINE_ERROR, stock, "2:2");
    tracked = trackLineError(tracked, stock, "2:2:price_changed");
    expect(visibleLineError(tracked)).toBeUndefined();

    tracked = trackLineError(tracked, stock, "2:2");
    expect(visibleLineError(tracked)).toBeUndefined();
  });

  it("um erro novo (outro objeto de estado) aparece de novo", () => {
    let tracked = trackLineError(NO_LINE_ERROR, stock, "2:2");
    tracked = trackLineError(tracked, stock, "1:2");
    tracked = trackLineError(tracked, { ...stock }, "1:2");

    expect(visibleLineError(tracked)).toBe("Só temos 2 unidades desse tamanho.");
  });

  it("sucesso e estado inicial não mostram nada", () => {
    expect(visibleLineError(NO_LINE_ERROR)).toBeUndefined();
    expect(trackLineError(NO_LINE_ERROR, null, "2:5")).toBe(NO_LINE_ERROR);
    expect(visibleLineError(trackLineError(NO_LINE_ERROR, { ok: true }, "2:5"))).toBeUndefined();
  });
});
