const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** Formata centavos como moeda brasileira. */
export function formatBRL(cents: number): string {
  return brl.format(cents / 100);
}

/** Parcelamento sem juros em `max` vezes; a parcela arredonda para cima. */
export function installments(cents: number, max: number): { count: number; eachCents: number } {
  return { count: max, eachCents: Math.ceil(cents / max) };
}

/** Preço à vista no Pix com desconto percentual. */
export function pixPrice(cents: number, percent: number): number {
  return Math.round((cents * (100 - percent)) / 100);
}
