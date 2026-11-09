import type { CatalogComponents } from "@katoshop/api-client";

export type Overview = CatalogComponents["schemas"]["OverviewOut"];
type ProductsByStatus = CatalogComponents["schemas"]["ProductsByStatus"];

export function statusCards(counts: ProductsByStatus): { label: string; value: number }[] {
  return [
    { label: "Ativos", value: counts.active },
    { label: "Rascunhos", value: counts.draft },
    { label: "Arquivados", value: counts.archived },
  ];
}

const REASONS: Record<string, string> = {
  initial: "Estoque inicial",
  adjustment: "Ajuste",
  damage: "Avaria",
  return: "Devolução",
  reservation: "Reserva",
  release: "Liberação",
  sale: "Venda",
};

export function movementReasonLabel(reason: string): string {
  return REASONS[reason] ?? reason;
}

export function formatDelta(delta: number): string {
  return delta > 0 ? `+${delta}` : String(delta);
}

const DATE_TIME = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatMovementDate(iso: string): string {
  return DATE_TIME.format(new Date(iso)).replace(",", "");
}
