"use client";

import type { CartComponents } from "@katoshop/api-client";
import { formatBRL } from "@katoshop/ui/money";
import { Minus, Plus, Trash2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useActionState } from "react";
import { removeItemAction, updateQuantityAction } from "../app/(shop)/carrinho/actions";
import { MAX_QUANTITY_PER_ITEM, messageForNotice } from "../lib/cart-messages";
import { CartNotice } from "./cart-notice";

type CartItem = CartComponents["schemas"]["ItemOut"];

const STEP =
  "inline-flex size-9 items-center justify-center rounded-[var(--radius)] border border-ks-border text-ks-fg transition-colors duration-[var(--duration-fast)] hover:bg-ks-fg/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ks-focus disabled:pointer-events-none disabled:opacity-40";

/**
 * Uma linha do carrinho. Os botões − e + e o "Remover" são submits do mesmo formulário com
 * actions diferentes (`formAction`), então funcionam sem JavaScript. O erro do cart (ex.:
 * estoque) aparece em linha.
 */
export function CartLine({ item }: { item: CartItem }) {
  const [quantityState, updateQuantity, updating] = useActionState(updateQuantityAction, null);
  const [removeState, removeItem, removing] = useActionState(removeItemAction, null);
  const pending = updating || removing;
  const error =
    (quantityState && !quantityState.ok && quantityState.message) ||
    (removeState && !removeState.ok && removeState.message) ||
    undefined;

  const ceiling = Math.min(item.available, MAX_QUANTITY_PER_ITEM);
  const notice = item.unavailable
    ? messageForNotice({
        code: "unavailable",
        old_price_cents: null,
        new_price_cents: null,
        quantity: null,
      })
    : item.notice
      ? messageForNotice(item.notice)
      : null;
  const muted = item.unavailable ? "opacity-50" : "";

  return (
    <li className="flex gap-4 border-b border-ks-border py-5">
      <div
        className={`relative aspect-[4/5] w-20 shrink-0 overflow-hidden rounded-[var(--radius)] bg-ks-surface sm:w-24 ${muted}`}
      >
        {item.image_url ? (
          <Image src={item.image_url} alt="" fill sizes="96px" className="object-cover" />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center text-[10px] uppercase tracking-wide text-ks-muted">
            Sem foto
          </span>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className={`flex flex-wrap items-start justify-between gap-x-4 gap-y-1 ${muted}`}>
          <div className="min-w-0">
            <h2 className="font-sans text-sm font-semibold normal-case">
              <Link href={`/p/${item.product_slug}`} className="hover:underline">
                {item.name}
              </Link>
            </h2>
            <p className="text-xs text-ks-muted">
              Cor {item.color_name}, tamanho {item.size_code}
            </p>
          </div>
          {item.unavailable ? (
            <p className="text-xs font-semibold uppercase tracking-wide text-ks-muted">
              Indisponível
            </p>
          ) : (
            <div className="text-right">
              <p className="font-mono text-accent">
                {formatBRL(item.unit_price_cents * item.quantity)}
              </p>
              {item.quantity > 1 && (
                <p className="font-mono text-xs text-ks-muted">
                  {formatBRL(item.unit_price_cents)} cada
                </p>
              )}
            </div>
          )}
        </div>

        {notice && <CartNotice message={notice} />}

        <form className="flex flex-wrap items-center gap-3">
          <input type="hidden" name="variant_id" value={item.variant_id} />
          {!item.unavailable && (
            <div className="flex items-center gap-2">
              <button
                type="submit"
                name="quantity"
                value={item.quantity - 1}
                formAction={updateQuantity}
                aria-label="Diminuir quantidade"
                disabled={pending || item.quantity <= 1}
                className={STEP}
              >
                <Minus aria-hidden className="size-4" />
              </button>
              <span className="sr-only">Quantidade</span>
              <output aria-live="polite" className="w-6 text-center font-mono tabular-nums">
                {item.quantity}
              </output>
              <button
                type="submit"
                name="quantity"
                value={item.quantity + 1}
                formAction={updateQuantity}
                aria-label="Aumentar quantidade"
                disabled={pending || item.quantity >= ceiling}
                className={STEP}
              >
                <Plus aria-hidden className="size-4" />
              </button>
            </div>
          )}
          <button
            type="submit"
            formAction={removeItem}
            disabled={pending}
            className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius)] px-2 text-xs font-semibold uppercase tracking-wide text-ks-muted transition-colors duration-[var(--duration-fast)] hover:bg-ks-fg/10 hover:text-ks-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ks-focus disabled:opacity-40"
          >
            <Trash2 aria-hidden className="size-4" />
            Remover
          </button>
        </form>
        <p role="status" aria-live="polite" className="text-sm text-red-400">
          {error}
        </p>
      </div>
    </li>
  );
}
