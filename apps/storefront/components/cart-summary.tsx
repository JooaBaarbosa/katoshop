import type { CartComponents } from "@katoshop/api-client";
import { Button } from "@katoshop/ui/button";
import { formatBRL } from "@katoshop/ui/money";
import { X } from "lucide-react";
import { removeCouponAction } from "../app/(shop)/carrinho/actions";
import { messageForCoupon } from "../lib/cart-messages";
import { CartActionButton } from "./cart-action-button";
import { CouponForm } from "./coupon-form";

type CartOut = CartComponents["schemas"]["CartOut"];

function Row({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className={strong ? "font-semibold uppercase tracking-wide" : "text-ks-muted"}>
        {label}
      </dt>
      <dd className={`font-mono ${strong ? "text-lg text-accent" : "text-ks-fg"}`}>{value}</dd>
    </div>
  );
}

/** Resumo: cupom, subtotal (só itens disponíveis, calculado pelo cart), desconto e total. */
export function CartSummary({ cart }: { cart: CartOut }) {
  const coupon = cart.coupon;
  return (
    <aside
      aria-label="Resumo do pedido"
      className="space-y-6 rounded-[var(--radius)] border border-ks-border p-5 lg:sticky lg:top-6"
    >
      <h2 className="text-2xl">Resumo</h2>

      {coupon ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm">
              Cupom <span className="font-mono font-semibold">{coupon.code}</span>
            </p>
            <CartActionButton
              action={removeCouponAction}
              variant="ghost"
              className="h-8 px-2 text-xs text-ks-muted hover:text-ks-fg"
            >
              <X aria-hidden className="size-4" />
              Remover cupom
            </CartActionButton>
          </div>
          {!coupon.valid && (
            <p className="text-sm text-red-400">
              {messageForCoupon(coupon.reason, coupon.min_order_cents)}
            </p>
          )}
        </div>
      ) : (
        <CouponForm />
      )}

      <dl className="space-y-2 border-t border-ks-border pt-4 text-sm">
        <Row label="Subtotal" value={formatBRL(cart.subtotal_cents)} />
        <Row
          label="Desconto"
          value={cart.discount_cents > 0 ? `− ${formatBRL(cart.discount_cents)}` : formatBRL(0)}
        />
        <Row label="Total" value={formatBRL(cart.total_cents)} strong />
      </dl>

      <div className="space-y-2">
        {cart.checkout_blocked && (
          <p className="text-sm font-semibold">Remova os itens indisponíveis para continuar.</p>
        )}
        <Button type="button" size="lg" className="w-full" disabled>
          Finalizar compra
        </Button>
        <p className="text-xs text-ks-muted">Checkout chega na próxima versão</p>
      </div>
    </aside>
  );
}
