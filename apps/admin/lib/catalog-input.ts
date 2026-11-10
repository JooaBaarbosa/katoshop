/** Conversões puras entre formulários do painel e o formato da API do catálogo. */

/** Cores de referência do catálogo (migração 0001), na ordem de exibição. */
export const COLORS = [
  { code: "PRT", name: "Preto", hex: "#111111" },
  { code: "BRC", name: "Branco", hex: "#F4F4F0" },
  { code: "CNZ", name: "Cinza mescla", hex: "#8C8C88" },
  { code: "OFW", name: "Off-white", hex: "#E8E3D6" },
  { code: "VRD", name: "Verde musgo", hex: "#4A5236" },
  { code: "AZM", name: "Azul marinho", hex: "#1E2A44" },
  { code: "MRR", name: "Marrom", hex: "#5A4030" },
] as const;

export const SIZES = ["PP", "P", "M", "G", "GG", "XG", "XGG"] as const;

export const STOCK_REASONS = [
  { value: "adjustment", label: "Ajuste" },
  { value: "damage", label: "Avaria" },
  { value: "return", label: "Devolução" },
  { value: "initial", label: "Estoque inicial" },
] as const;

export const STATUS_LABELS: Record<string, string> = {
  draft: "Rascunho",
  active: "Ativo",
  archived: "Arquivado",
};

export function colorName(code: string): string {
  return COLORS.find((color) => color.code === code)?.name ?? code;
}

/** "129,90", "129.90", "R$ 1.299,90" ou "129" em centavos; null se não for preço válido. */
export function parsePriceCents(input: string): number | null {
  const text = input.replace(/^\s*R\$\s*/, "").trim();
  const match = /^(\d{1,3}(?:\.\d{3})+|\d+)(?:[,.](\d{1,2}))?$/.exec(text);
  if (!match) return null;
  const reais = Number((match[1] ?? "").replaceAll(".", ""));
  const cents = Number((match[2] ?? "").padEnd(2, "0"));
  const total = reais * 100 + cents;
  return Number.isSafeInteger(total) ? total : null;
}

export function formatCentsInput(cents: number): string {
  return `${Math.floor(cents / 100)},${String(cents % 100).padStart(2, "0")}`;
}

/** Uma linha por atributo, "chave: valor"; linhas sem dois pontos são ignoradas. */
export function parseAttributes(text: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const index = line.indexOf(":");
    if (index <= 0) continue;
    const key = line.slice(0, index).trim();
    const value = line.slice(index + 1).trim();
    if (key && value) result[key] = value;
  }
  return result;
}

export function formatAttributes(attributes: Record<string, unknown>): string {
  return Object.entries(attributes)
    .filter(([, value]) => typeof value === "string" || typeof value === "number")
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join("\n");
}

/** Inteiro diferente de zero dentro do limite da API (±1.000.000). */
export function parseDelta(input: string): number | null {
  const text = input.trim();
  if (!/^[+-]?\d+$/.test(text)) return null;
  const value = Number(text);
  if (value === 0 || Math.abs(value) > 1_000_000) return null;
  return value;
}

type PublishInput = {
  variants: { active: boolean; effective_price_cents: number }[];
  images: unknown[];
};

/** Mesmas regras de `catalog.domain.publishing`, para o checklist antes de publicar. */
export function publishBlockers(product: PublishInput): string[] {
  const active = product.variants.filter((variant) => variant.active);
  const blockers: string[] = [];
  if (active.length === 0) blockers.push("no_active_variant");
  if (product.images.length < 1) blockers.push("no_image");
  if (active.some((variant) => variant.effective_price_cents <= 0)) blockers.push("no_price");
  return blockers;
}

function rank(list: readonly string[], value: string): number {
  const index = list.indexOf(value);
  return index === -1 ? list.length : index;
}

const COLOR_CODES: readonly string[] = COLORS.map((color) => color.code);

export function sortVariants<T extends { color_code: string; size_code: string }>(
  variants: T[],
): T[] {
  return [...variants].sort(
    (a, b) =>
      rank(COLOR_CODES, a.color_code) - rank(COLOR_CODES, b.color_code) ||
      rank(SIZES, a.size_code) - rank(SIZES, b.size_code),
  );
}
