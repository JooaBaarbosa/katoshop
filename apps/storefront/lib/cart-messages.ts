import type { CartComponents } from "@katoshop/api-client";
import { formatBRL } from "@katoshop/ui/money";

export type Notice = CartComponents["schemas"]["NoticeOut"];

/** Texto pt-BR de um aviso do item. Só usa os dados reais do aviso; sem eles, não inventa número. */
export function messageForNotice(notice: Notice): string {
  switch (notice.code) {
    case "price_changed":
      return notice.old_price_cents !== null && notice.new_price_cents !== null
        ? `O preço mudou de ${formatBRL(notice.old_price_cents)} para ${formatBRL(notice.new_price_cents)}.`
        : "O preço deste item mudou.";
    case "quantity_reduced":
      return notice.quantity !== null
        ? `Ajustamos a quantidade para ${notice.quantity}, que é o que temos em estoque.`
        : "Ajustamos a quantidade ao que temos em estoque.";
    case "unavailable":
      return "Este item esgotou ou saiu da loja. Remova para continuar.";
  }
}

export const COUPON_UNAVAILABLE = "Não foi possível validar o cupom agora.";
const COUPON_FALLBACK = "Este cupom não vale agora.";

// O cart repassa o motivo completo do promotions (`promotions.coupon.<motivo>`), ou
// `promotions.unavailable` quando não conseguiu avaliar.
const COUPON_MESSAGES: Record<string, string> = {
  "promotions.coupon.not_found": "Cupom não encontrado.",
  "promotions.coupon.inactive": "Este cupom não está ativo.",
  "promotions.coupon.not_started": "Este cupom ainda não começou a valer.",
  "promotions.coupon.expired": "Este cupom expirou.",
  "promotions.coupon.no_eligible_items": "Nenhum item do carrinho vale para este cupom.",
  "promotions.coupon.usage_limit_reached": "Este cupom atingiu o limite de usos.",
  "promotions.coupon.login_required": "Entre na sua conta para usar este cupom.",
  "promotions.coupon.customer_limit_reached": "Você já usou este cupom.",
  "promotions.unavailable": COUPON_UNAVAILABLE,
};

/**
 * Texto pt-BR do motivo de um cupom recusado; `minOrderCents` para o pedido mínimo.
 * O mínimo conta só os itens elegíveis do cupom (categorias e coleções), e o cart não diz se o
 * cupom tem restrição, então a frase fala sempre em "itens válidos".
 */
export function messageForCoupon(
  reason: string | null | undefined,
  minOrderCents?: number | null,
): string {
  if (reason === "promotions.coupon.min_order_not_met") {
    return typeof minOrderCents === "number"
      ? `Pedido mínimo de ${formatBRL(minOrderCents)} em itens válidos para este cupom.`
      : "Este cupom pede um valor mínimo de pedido.";
  }
  return (reason && COUPON_MESSAGES[reason]) || COUPON_FALLBACK;
}

/** Teto por SKU do cart (spec §4.3); o botão + respeita também o estoque da linha. */
export const MAX_QUANTITY_PER_ITEM = 20;

type LineSnapshot = Pick<
  CartComponents["schemas"]["ItemOut"],
  "quantity" | "available" | "unavailable" | "unit_price_cents" | "notice"
>;

/**
 * Versão visível de uma linha do carrinho. O formulário envia a versão, a action a devolve junto
 * com o erro, e a linha só mostra o erro enquanto a versão for a mesma: depois que o carrinho
 * muda (outra ação, outra aba, evento do catálogo), o erro antigo some.
 */
export function lineVersion(item: LineSnapshot): string {
  return [
    item.quantity,
    item.available,
    item.unavailable ? 1 : 0,
    item.unit_price_cents,
    item.notice?.code ?? "",
  ].join(":");
}

/** Título do /carrinho, que recebe o foco quando uma linha some depois de "Remover". */
export const CART_HEADING_ID = "carrinho-titulo";
