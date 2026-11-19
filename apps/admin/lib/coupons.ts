/** Conversões puras entre o formulário de cupons e o formato da API do promotions. */
import type { PromotionsComponents } from "@katoshop/api-client";
import { formatBRL } from "@katoshop/ui/money";

type Schemas = PromotionsComponents["schemas"];
export type Coupon = Schemas["CouponOut"];
export type CouponKind = Coupon["kind"];

export const TIME_ZONE = "America/Sao_Paulo";

/** Teto do formulário para valores em reais (R$ 100.000,00); o servidor aceita até 2 bilhões. */
export const MAX_REAIS_CENTS = 10_000_000;
/** Mesmo limite do `PositiveInt` do promotions. */
const MAX_COUNT = 2_000_000_000;
const MAX_PERCENT = 90;
const MAX_DESCRIPTION = 500;

export const KIND_LABELS: Record<CouponKind, string> = {
  percent: "Percentual",
  fixed: "Valor fixo",
};

export const MESSAGES = {
  code: "Use de 3 a 32 caracteres: letras sem acento, números e hífen.",
  kind: "Escolha o tipo de desconto.",
  percent: "Informe um percentual inteiro de 1 a 90.",
  fixed: "Informe um valor em reais maior que zero, como 10,50, até R$ 100.000,00.",
  value: "Confira o valor: percentual inteiro de 1 a 90 ou valor fixo maior que zero.",
  min_order: "Informe um valor em reais maior que zero, como 99,90, ou deixe vazio.",
  datetime: "Informe uma data e hora válidas.",
  ends_after: "O fim deve ser depois do início.",
  count: "Use um número inteiro a partir de 1, ou deixe vazio.",
  description: "A descrição aceita no máximo 500 caracteres.",
  category_slugs: "Escolha categorias da lista.",
  collection_slugs: "Escolha coleções da lista.",
} as const;

const CODE_RE = /^[A-Z0-9-]{3,32}$/;
// eslint-disable-next-line no-control-regex
const ASCII_RE = /^[\x00-\x7F]*$/;

/** Mesma regra de `promotions.domain.coupons.normalize_code`: strip, ASCII e upper. */
export function normalizeCouponCode(raw: string): string | null {
  const stripped = raw.trim();
  if (!ASCII_RE.test(stripped)) return null;
  const code = stripped.toUpperCase();
  return CODE_RE.test(code) ? code : null;
}

/**
 * Reais em centavos, lidos como texto (sem float): "10", "10,50", "10.50" ou "R$ 10,50".
 * Recusa zero, negativos, mais de 2 decimais, separador de milhar e valores acima do teto.
 */
export function parseReaisCents(input: string, max = MAX_REAIS_CENTS): number | null {
  const text = input.replace(/^\s*R\$\s*/, "").trim();
  const match = /^(\d{1,9})(?:[.,](\d{1,2}))?$/.exec(text);
  if (!match) return null;
  const cents = Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
  return cents >= 1 && cents <= max ? cents : null;
}

function parseCount(text: string): number | null {
  if (!/^\d{1,10}$/.test(text)) return null;
  const value = Number(text);
  return value >= 1 && value <= MAX_COUNT ? value : null;
}

const PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

type WallClock = { year: number; month: number; day: number; hour: number; minute: number; second: number };

function wallClockAt(instant: number): WallClock {
  const parts = Object.fromEntries(
    PARTS.formatToParts(new Date(instant)).map((part) => [part.type, part.value]),
  );
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    second: Number(parts.second),
  };
}

function asUtc(clock: WallClock): number {
  return Date.UTC(clock.year, clock.month - 1, clock.day, clock.hour, clock.minute, clock.second);
}

/** Deslocamento do fuso (ms) no instante dado, pela base de fusos do Intl. */
function offsetAt(instant: number): number {
  return asUtc(wallClockAt(instant - (instant % 1000))) - (instant - (instant % 1000));
}

/**
 * Valor de `<input type="datetime-local">` (hora de São Paulo) em ISO UTC. Usa a regra real do
 * fuso (inclusive horário de verão, se voltar a existir), não um -03:00 fixo.
 */
export function saoPauloLocalToUtc(local: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(local.trim());
  if (!match) return null;
  const clock: WallClock = {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
    second: Number(match[6] ?? "0"),
  };
  const guess = asUtc(clock);
  if (Number.isNaN(guess)) return null;
  // data impossível (30/02, mês 13): Date.UTC normaliza, então o relógio de volta não bate
  const check = new Date(guess);
  if (
    check.getUTCFullYear() !== clock.year ||
    check.getUTCMonth() + 1 !== clock.month ||
    check.getUTCDate() !== clock.day ||
    clock.hour > 23 ||
    clock.minute > 59 ||
    clock.second > 59
  ) {
    return null;
  }
  let instant = guess - offsetAt(guess);
  const second = guess - offsetAt(instant);
  if (second !== instant) instant = second;
  return new Date(instant).toISOString();
}

/** ISO UTC da API para o `defaultValue` do datetime-local, na hora de São Paulo. */
export function utcToSaoPauloLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const instant = Date.parse(iso);
  if (Number.isNaN(instant)) return "";
  const c = wallClockAt(instant);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${String(c.year).padStart(4, "0")}-${pad(c.month)}-${pad(c.day)}T${pad(c.hour)}:${pad(c.minute)}`;
}

/** Remove repetidos (mantendo a ordem) e, com `known`, o que não veio do catálogo. */
export function onlyKnown(values: readonly string[], known?: readonly string[]): string[] {
  const allowed = known ? new Set(known) : null;
  return [...new Set(values)].filter((value) => !allowed || allowed.has(value));
}

export type CouponFields = {
  description: string;
  kind: CouponKind;
  value: number;
  min_order_cents: number | null;
  starts_at: string | null;
  ends_at: string | null;
  category_slugs: string[];
  collection_slugs: string[];
  max_uses_total: number | null;
  max_uses_per_customer: number | null;
};

export type CouponCreate = CouponFields & { code: string; active: boolean };

export type Parsed<T> = { ok: true; body: T } | { ok: false; fieldErrors: Record<string, string> };

type ParseOptions = {
  /** Categorias e coleções carregadas do catalog: o resto é ignorado. */
  categories?: readonly string[];
  collections?: readonly string[];
};

function text(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function list(formData: FormData, name: string): string[] {
  return formData
    .getAll(name)
    .filter((value): value is string => typeof value === "string")
    .map((value) => value.trim())
    .filter(Boolean);
}

/**
 * Lê o formulário de cupom com as mesmas regras do servidor. Na criação lê código e ativo; na
 * edição (`mode: "update"`) os dois ficam fora (o código é imutável e o ativo tem rotas próprias).
 */
export function parseCouponForm(
  formData: FormData,
  options?: ParseOptions & { mode?: "create" },
): Parsed<CouponCreate>;
export function parseCouponForm(
  formData: FormData,
  options: ParseOptions & { mode: "update" },
): Parsed<CouponFields>;
export function parseCouponForm(
  formData: FormData,
  options: ParseOptions & { mode?: "create" | "update" } = {},
): Parsed<CouponFields | CouponCreate> {
  const fieldErrors: Record<string, string> = {};
  const create = options.mode !== "update";

  const code = create ? normalizeCouponCode(text(formData, "code")) : null;
  if (create && code === null) fieldErrors.code = MESSAGES.code;

  const description = text(formData, "description");
  if (description.length > MAX_DESCRIPTION) fieldErrors.description = MESSAGES.description;

  const kindText = text(formData, "kind");
  const kind = kindText === "percent" || kindText === "fixed" ? kindText : null;
  if (kind === null) fieldErrors.kind = MESSAGES.kind;

  const valueText = text(formData, "value");
  let value: number | null = null;
  if (kind === "percent") {
    value = /^\d{1,2}$/.test(valueText) ? Number(valueText) : null;
    if (value === null || value < 1 || value > MAX_PERCENT) {
      value = null;
      fieldErrors.value = MESSAGES.percent;
    }
  } else if (kind === "fixed") {
    value = parseReaisCents(valueText);
    if (value === null) fieldErrors.value = MESSAGES.fixed;
  }

  const minOrderText = text(formData, "min_order");
  const minOrder = minOrderText ? parseReaisCents(minOrderText) : null;
  if (minOrderText && minOrder === null) fieldErrors.min_order = MESSAGES.min_order;

  const dates: Record<"starts_at" | "ends_at", string | null> = { starts_at: null, ends_at: null };
  for (const name of ["starts_at", "ends_at"] as const) {
    const raw = text(formData, name);
    if (!raw) continue;
    dates[name] = saoPauloLocalToUtc(raw);
    if (dates[name] === null) fieldErrors[name] = MESSAGES.datetime;
  }
  if (dates.starts_at && dates.ends_at && Date.parse(dates.ends_at) <= Date.parse(dates.starts_at)) {
    fieldErrors.ends_at = MESSAGES.ends_after;
  }

  const counts: Record<"max_uses_total" | "max_uses_per_customer", number | null> = {
    max_uses_total: null,
    max_uses_per_customer: null,
  };
  for (const name of ["max_uses_total", "max_uses_per_customer"] as const) {
    const raw = text(formData, name);
    if (!raw) continue;
    counts[name] = parseCount(raw);
    if (counts[name] === null) fieldErrors[name] = MESSAGES.count;
  }

  if (Object.keys(fieldErrors).length > 0 || kind === null || value === null) {
    return { ok: false, fieldErrors };
  }

  const fields: CouponFields = {
    description,
    kind,
    value,
    min_order_cents: minOrder,
    starts_at: dates.starts_at,
    ends_at: dates.ends_at,
    category_slugs: onlyKnown(list(formData, "category_slugs"), options.categories),
    collection_slugs: onlyKnown(list(formData, "collection_slugs"), options.collections),
    max_uses_total: counts.max_uses_total,
    max_uses_per_customer: counts.max_uses_per_customer,
  };
  if (!create || code === null) return { ok: true, body: fields };
  return { ok: true, body: { code, ...fields, active: formData.get("active") === "on" } };
}

const SERVER_FIELD: Record<string, { field: string; message: string }> = {
  code: { field: "code", message: MESSAGES.code },
  description: { field: "description", message: MESSAGES.description },
  kind: { field: "kind", message: MESSAGES.kind },
  value: { field: "value", message: MESSAGES.value },
  min_order_cents: { field: "min_order", message: MESSAGES.min_order },
  starts_at: { field: "starts_at", message: MESSAGES.datetime },
  ends_at: { field: "ends_at", message: MESSAGES.ends_after },
  category_slugs: { field: "category_slugs", message: MESSAGES.category_slugs },
  collection_slugs: { field: "collection_slugs", message: MESSAGES.collection_slugs },
  max_uses_total: { field: "max_uses_total", message: MESSAGES.count },
  max_uses_per_customer: { field: "max_uses_per_customer", message: MESSAGES.count },
};

/**
 * Erros do 422 `request.validation` (`body.<campo>[.índice]`, texto do servidor) nos campos do
 * formulário, com as mensagens pt-BR do painel. Chaves que não são de campo ficam de fora.
 */
export function couponFieldErrors(
  errors: Record<string, string> | undefined,
): Record<string, string> | undefined {
  if (!errors) return undefined;
  const result: Record<string, string> = {};
  for (const key of Object.keys(errors)) {
    const name = key.replace(/^body\./, "").split(".")[0] ?? "";
    const mapped = SERVER_FIELD[name];
    if (mapped && !(mapped.field in result)) result[mapped.field] = mapped.message;
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

export function couponValueLabel(coupon: Pick<Coupon, "kind" | "value">): string {
  return coupon.kind === "percent" ? `${coupon.value}%` : formatBRL(coupon.value);
}

export function couponConditions(
  coupon: Pick<
    Coupon,
    | "min_order_cents"
    | "category_slugs"
    | "collection_slugs"
    | "max_uses_total"
    | "max_uses_per_customer"
  >,
): string[] {
  const items: string[] = [];
  if (coupon.min_order_cents !== null) {
    items.push(`Pedido mínimo de ${formatBRL(coupon.min_order_cents)}`);
  }
  if (coupon.category_slugs.length > 0) {
    items.push(`Categorias: ${coupon.category_slugs.join(", ")}`);
  }
  if (coupon.collection_slugs.length > 0) {
    items.push(`Coleções: ${coupon.collection_slugs.join(", ")}`);
  }
  if (coupon.max_uses_total !== null) {
    items.push(
      `Até ${coupon.max_uses_total} ${coupon.max_uses_total === 1 ? "uso" : "usos"} no total`,
    );
  }
  if (coupon.max_uses_per_customer !== null) {
    const n = coupon.max_uses_per_customer;
    items.push(`${n} ${n === 1 ? "uso" : "usos"} por cliente`);
  }
  return items.length > 0 ? items : ["Loja toda"];
}

const FLASH: Record<string, string> = {
  criado: "Cupom criado.",
  salvo: "Alterações salvas.",
  excluido: "Cupom excluído.",
};

/** Aviso da lista depois do redirect (`?aviso=`): só chaves conhecidas, nunca texto da URL. */
export function flashMessage(key: string | undefined): string | null {
  return key !== undefined && Object.hasOwn(FLASH, key) ? (FLASH[key] ?? null) : null;
}
