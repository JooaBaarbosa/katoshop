export const SORTS = ["relevance", "newest", "price_asc", "price_desc"] as const;
export type Sort = (typeof SORTS)[number];

export type CatalogFilters = {
  size: string[];
  color: string[];
  priceMin?: number;
  priceMax?: number;
  sort: Sort;
  q?: string;
};

export type RawSearchParams = Record<string, string | string[] | undefined>;

// Mesmos limites da API de catálogo: valor fora deles seria 422, então nem é enviado.
const CODE = /^[A-Z]{1,4}$/;
const MAX_CODES = 20;
const WHOLE_REAIS = /^\d{1,8}$/;
const INT4_MAX = 2 ** 31 - 1;
// eslint-disable-next-line no-control-regex -- a API recusa caracteres de controle na busca
const CONTROL_CHARS = /[\x00-\x1f\x7f]/g;

function all(value: string | string[] | undefined): string[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

function first(value: string | string[] | undefined): string | undefined {
  return all(value)[0];
}

function codes(value: string | string[] | undefined): string[] {
  const valid = all(value).filter((code) => CODE.test(code));
  return [...new Set(valid)].slice(0, MAX_CODES);
}

/** Preço da URL em reais inteiros, devolvido em centavos; qualquer outra coisa é ignorada. */
function priceCents(value: string | string[] | undefined): number | undefined {
  const raw = first(value);
  if (raw === undefined || !WHOLE_REAIS.test(raw)) return undefined;
  const cents = Number(raw) * 100;
  return cents <= INT4_MAX ? cents : undefined;
}

function isSort(value: string | undefined): value is Sort {
  return SORTS.includes(value as Sort);
}

/** Ordem padrão: relevância quando há busca, novidades nas demais listagens. */
export function defaultSort(q: string | undefined): Sort {
  return q === undefined ? "newest" : "relevance";
}

/** Lê os filtros da URL da loja. Valores inválidos são ignorados, nunca derrubam a página. */
export function parseFilters(sp: RawSearchParams): CatalogFilters {
  const q = first(sp.q)?.replace(CONTROL_CHARS, " ").trim() || undefined;
  const sort = first(sp.ordem);
  const filters: CatalogFilters = {
    size: codes(sp.tamanho),
    color: codes(sp.cor),
    sort: isSort(sort) ? sort : defaultSort(q),
  };
  const priceMin = priceCents(sp.preco_min);
  const priceMax = priceCents(sp.preco_max);
  if (priceMin !== undefined) filters.priceMin = priceMin;
  if (priceMax !== undefined) filters.priceMax = priceMax;
  if (q !== undefined) filters.q = q;
  return filters;
}

/** Filtros de volta para a URL da loja (preço em reais, ordem padrão omitida). */
export function toSearchParams(f: CatalogFilters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q !== undefined) sp.set("q", f.q);
  for (const size of f.size) sp.append("tamanho", size);
  for (const color of f.color) sp.append("cor", color);
  if (f.priceMin !== undefined) sp.set("preco_min", String(Math.floor(f.priceMin / 100)));
  if (f.priceMax !== undefined) sp.set("preco_max", String(Math.floor(f.priceMax / 100)));
  if (f.sort !== defaultSort(f.q)) sp.set("ordem", f.sort);
  return sp;
}

/** Converte a URLSearchParams em objeto no formato que o Next entrega em `searchParams`. */
export function fromSearchParams(sp: URLSearchParams): RawSearchParams {
  const out: Record<string, string | string[]> = {};
  for (const [key, value] of sp) {
    const current = out[key];
    out[key] = current === undefined ? value : [...all(current), value];
  }
  return out;
}

/** Há algum filtro além da busca e da ordem? */
export function hasActiveFilters(f: CatalogFilters): boolean {
  return f.size.length > 0 || f.color.length > 0 || f.priceMin !== undefined || f.priceMax !== undefined;
}
