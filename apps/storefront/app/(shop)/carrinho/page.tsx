import { Button } from "@katoshop/ui/button";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { CartActionButton } from "../../../components/cart-action-button";
import { CartLine } from "../../../components/cart-line";
import { CartNoticesBar } from "../../../components/cart-notice";
import { CartSummary } from "../../../components/cart-summary";
import { CART_FLASH_COOKIE, CART_FLASH_MERGE_ADJUSTED, getCart } from "../../../lib/cart";
import { CART_HEADING_ID } from "../../../lib/cart-messages";
import { removeUnavailableAction } from "./actions";

export const metadata: Metadata = {
  title: "Carrinho",
  description: "Seu carrinho na KatoShop, loja demonstrativa.",
  robots: { index: false, follow: false },
};

/**
 * Renderizado por requisição (R21, o layout é dinâmico). Só leitura (R18): o flash do merge é
 * lido aqui e apagado pelo "Entendi" (ackNoticesAction) ou pelo maxAge de 120 s.
 */
export default async function CartPage() {
  const view = await getCart();
  // R22: cart fora do ar cai na página de erro da marca, em vez de mostrar um carrinho vazio falso
  if (view.unavailable) throw new Error("cart unavailable");

  const mergeAdjusted =
    (await cookies()).get(CART_FLASH_COOKIE)?.value === CART_FLASH_MERGE_ADJUSTED;
  const itemNotices = view.items.some((item) => item.notice !== null);
  const hasUnavailable = view.items.some((item) => item.unavailable);

  return (
    <div className="space-y-6">
      <h1 id={CART_HEADING_ID} tabIndex={-1} className="text-5xl focus:outline-none">
        Carrinho
      </h1>
      <CartNoticesBar mergeAdjusted={mergeAdjusted} itemNotices={itemNotices} />

      {view.items.length === 0 ? (
        <div className="space-y-4 py-10">
          <p className="text-lg">Seu carrinho está vazio.</p>
          <Button asChild>
            <Link href="/busca">Ver todas as peças</Link>
          </Button>
        </div>
      ) : (
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <section aria-label="Itens do carrinho">
            {hasUnavailable && (
              <div className="flex justify-end">
                <CartActionButton action={removeUnavailableAction} variant="ghost">
                  Limpar indisponíveis
                </CartActionButton>
              </div>
            )}
            <ul className="border-t border-ks-border">
              {view.items.map((item) => (
                <CartLine key={item.variant_id} item={item} />
              ))}
            </ul>
          </section>
          <CartSummary cart={view} />
        </div>
      )}
    </div>
  );
}
