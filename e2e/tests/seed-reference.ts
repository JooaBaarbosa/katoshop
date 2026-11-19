import { adjustStock, adminProduct, type AdminVariant, type Api, variantOf } from "./support";

/**
 * Valores do seed (scripts/seed/data.py) das variantes que os specs alteram ou cujo preço
 * conferem. Fonte da verdade para restaurar (R26): um spec interrompido no meio deixa a
 * variante fora do seed, e o próximo começa devolvendo estes valores.
 */
export type SeedVariant = {
  slug: string;
  name: string;
  color: string;
  size: string;
  /** preço próprio da variante; null = herda o preço base */
  priceCents: number | null;
  basePriceCents: number;
  stock: number;
};

export function seedPrice(ref: SeedVariant): number {
  return ref.priceCents ?? ref.basePriceCents;
}

export const SEED = {
  boneCinzaM: {
    slug: "bone-lavado-cinza",
    name: "Boné lavado cinza",
    color: "CNZ",
    size: "M",
    priceCents: null,
    basePriceCents: 11900,
    stock: 18,
  },
  bermudaCinzaM: {
    slug: "bermuda-moletom",
    name: "Bermuda de moletom",
    color: "CNZ",
    size: "M",
    priceCents: null,
    basePriceCents: 15900,
    stock: 10,
  },
  camisetaPretaM: {
    slug: "camiseta-pesada-preta",
    name: "Camiseta pesada preta",
    color: "PRT",
    size: "M",
    priceCents: null,
    basePriceCents: 12900,
    stock: 18,
  },
} as const satisfies Record<string, SeedVariant>;

async function current(
  api: Api,
  token: string,
  ref: SeedVariant,
): Promise<{ productId: string; variant: AdminVariant }> {
  const product = await adminProduct(api, token, ref.slug);
  return { productId: product.id, variant: variantOf(product, ref.color, ref.size) };
}

/** Leva o estoque da variante a um valor absoluto (ajuste "adjustment" pela diferença). */
export async function setStock(
  api: Api,
  token: string,
  ref: SeedVariant,
  target: number,
  note: string,
): Promise<void> {
  const { variant } = await current(api, token, ref);
  const delta = target - variant.stock_on_hand;
  if (delta !== 0) await adjustStock(api, token, variant.id, delta, note);
}

/**
 * Devolve preço e estoque da variante aos valores do seed, pela API de admin; avisa no log
 * (`log`, no início do spec) quando havia sobra de uma execução interrompida. No `finally` o spec
 * chama com `log: false`: ali a diferença é a do próprio teste. Devolve a variante já curada.
 */
export async function healVariant(
  api: Api,
  token: string,
  ref: SeedVariant,
  { log = true }: { log?: boolean } = {},
): Promise<{ productId: string; variant: AdminVariant }> {
  let state = await current(api, token, ref);
  const label = `${ref.slug} ${ref.color} ${ref.size}`;
  if (state.variant.price_cents !== ref.priceCents) {
    if (log)
      console.log(
        `seed-reference: ${label} com preço ${state.variant.price_cents}; restaurando ${ref.priceCents}`,
      );
    const patched = await api.call("PATCH", `/catalog/v1/admin/variants/${state.variant.id}`, {
      token,
      body: { version: state.variant.version, price_cents: ref.priceCents },
    });
    if (patched.status !== 200) throw new Error(`falha ao restaurar o preço de ${label}`);
  }
  if (log && state.variant.stock_on_hand !== ref.stock) {
    console.log(
      `seed-reference: ${label} com estoque ${state.variant.stock_on_hand}; restaurando ${ref.stock}`,
    );
  }
  await setStock(api, token, ref, ref.stock, "Teste e2e: estoque devolvido ao valor do seed");
  state = await current(api, token, ref);
  return state;
}
