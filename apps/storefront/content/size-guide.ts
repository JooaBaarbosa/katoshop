/** Tabelas de medidas da loja demo, em centímetros, com a peça estendida. */
export type SizeGuideTable = {
  title: string;
  /** Nome de cada medida, na ordem dos valores de cada linha. */
  measures: string[];
  rows: { size: string; values: number[] }[];
};

export const SIZE_GUIDE_NOTE = "Medidas da loja demo, em centímetros, com a peça estendida.";

export const SIZE_GUIDE = {
  camisetas: {
    title: "Camisetas",
    measures: ["Largura do peito", "Comprimento", "Manga"],
    rows: [
      { size: "PP", values: [48, 68, 20] },
      { size: "P", values: [51, 70, 21] },
      { size: "M", values: [54, 72, 22] },
      { size: "G", values: [57, 74, 23] },
      { size: "GG", values: [60, 76, 24] },
      { size: "XG", values: [63, 78, 25] },
      { size: "XGG", values: [66, 80, 26] },
    ],
  },
  moletons: {
    title: "Moletons",
    measures: ["Largura do peito", "Comprimento", "Manga"],
    rows: [
      { size: "PP", values: [52, 66, 58] },
      { size: "P", values: [55, 68, 60] },
      { size: "M", values: [58, 70, 62] },
      { size: "G", values: [61, 72, 64] },
      { size: "GG", values: [64, 74, 65] },
      { size: "XG", values: [67, 76, 66] },
      { size: "XGG", values: [70, 78, 67] },
    ],
  },
  calcas: {
    title: "Calças",
    measures: ["Cintura", "Quadril", "Comprimento"],
    rows: [
      { size: "PP", values: [36, 48, 100] },
      { size: "P", values: [38, 50, 102] },
      { size: "M", values: [40, 52, 104] },
      { size: "G", values: [42, 54, 106] },
      { size: "GG", values: [44, 56, 108] },
      { size: "XG", values: [46, 58, 110] },
      { size: "XGG", values: [48, 60, 112] },
    ],
  },
} satisfies Record<string, SizeGuideTable>;

export type SizeGuideCategory = keyof typeof SIZE_GUIDE;

/** Tabelas para a categoria do produto; se a categoria não tiver tabela própria, todas. */
export function sizeGuideFor(categorySlug: string): SizeGuideTable[] {
  const table = (SIZE_GUIDE as Record<string, SizeGuideTable>)[categorySlug];
  return table ? [table] : Object.values(SIZE_GUIDE);
}
