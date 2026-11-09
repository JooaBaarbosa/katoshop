import { describe, expect, it } from "vitest";
import { formatDelta, formatMovementDate, movementReasonLabel, statusCards } from "../lib/overview";

describe("statusCards", () => {
  it("mostra os números da API, na ordem ativos, rascunhos, arquivados", () => {
    expect(statusCards({ active: 12, draft: 3, archived: 0 })).toEqual([
      { label: "Ativos", value: 12 },
      { label: "Rascunhos", value: 3 },
      { label: "Arquivados", value: 0 },
    ]);
  });
});

describe("movementReasonLabel", () => {
  it.each([
    ["initial", "Estoque inicial"],
    ["adjustment", "Ajuste"],
    ["damage", "Avaria"],
    ["return", "Devolução"],
    ["reservation", "Reserva"],
    ["release", "Liberação"],
    ["sale", "Venda"],
  ])("%s vira %s", (reason, label) => {
    expect(movementReasonLabel(reason)).toBe(label);
  });

  it("motivo desconhecido aparece como veio", () => {
    expect(movementReasonLabel("novo_motivo")).toBe("novo_motivo");
  });
});

describe("formatDelta", () => {
  it("entrada com sinal de mais, saída com sinal de menos", () => {
    expect(formatDelta(5)).toBe("+5");
    expect(formatDelta(-3)).toBe("-3");
    expect(formatDelta(0)).toBe("0");
  });
});

describe("formatMovementDate", () => {
  it("data e hora de Brasília", () => {
    expect(formatMovementDate("2026-11-09T15:04:00Z")).toBe("09/11/2026 12:04");
  });
});
