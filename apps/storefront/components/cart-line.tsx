"use client";

import type { CartComponents } from "@katoshop/api-client";
import { formatBRL } from "@katoshop/ui/money";
import { Minus, Plus, Trash2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useActionState, useEffect, useRef, useState } from "react";
import { removeItemAction, updateQuantityAction } from "../app/(shop)/carrinho/actions";
import {
  CART_HEADING_ID,
  lineVersion,
  MAX_QUANTITY_PER_ITEM,
  messageForNotice,
} from "../lib/cart-messages";
import { NO_LINE_ERROR, trackLineError, visibleLineError } from "../lib/line-error";
import { CartNotice } from "./cart-notice";

type CartItem = CartComponents["schemas"]["ItemOut"];

const STEP =
  "inline-flex size-9 items-center justify-center rounded-[var(--radius)] border border-ks-border text-ks-fg transition-colors duration-[var(--duration-fast)] hover:bg-ks-fg/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ks-focus disabled:pointer-events-none disabled:opacity-40";

/**
 * Uma linha do carrinho. Cada botão (−, + e Remover) tem o próprio formulário com os campos em
 * inputs ocultos: um submit com `name`/`value` e `formAction` de função perde o campo (o React
 * troca o `name` no HTML do servidor e monta o FormData sem o submitter). Funciona sem
 * JavaScript. O erro do cart (ex.: estoque) aparece em linha no render que o traz (já com os
 * dados do refresh) e some na próxima mudança da linha (lib/line-error.ts).
 */
export function CartLine({ item }: { item: CartItem }) {
  const [quantityState, updateQuantity, updating] = useActionState(updateQuantityAction, null);
  const [removeState, removeItem, removing] = useActionState(removeItemAction, null);
  const pending = updating || removing;
  const version = lineVersion(item);

  // "Guardar informação de renders anteriores" (setState durante o render, com guarda): vale
  // também no primeiro render do HTML sem JavaScript, que já chega com o estado da action.
  const [quantityError, setQuantityError] = useState(NO_LINE_ERROR);
  const [removeError, setRemoveError] = useState(NO_LINE_ERROR);
  const nextQuantityError = trackLineError(quantityError, quantityState, version);
  const nextRemoveError = trackLineError(removeError, removeState, version);
  if (nextQuantityError !== quantityError) setQuantityError(nextQuantityError);
  if (nextRemoveError !== removeError) setRemoveError(nextRemoveError);
  const error = visibleLineError(nextQuantityError) ?? visibleLineError(nextRemoveError);

  // Com JavaScript: a linha removida desmonta e o foco iria para o body; leva ao título.
  const removeRequested = useRef(false);
  useEffect(() => {
    if (removeState && !removeState.ok) removeRequested.current = false;
  }, [removeState]);
  useEffect(() => {
    const requested = removeRequested;
    return () => {
      if (requested.current) document.getElementById(CART_HEADING_ID)?.focus();
    };
  }, []);

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
  const lineFields = <input type="hidden" name="variant_id" value={item.variant_id} />;

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

        <div className="flex flex-wrap items-center gap-3">
          {!item.unavailable && (
            <div className="flex items-center gap-2">
              <form action={updateQuantity}>
                {lineFields}
                <input type="hidden" name="quantity" value={item.quantity - 1} />
                <button
                  type="submit"
                  aria-label="Diminuir quantidade"
                  disabled={pending || item.quantity <= 1}
                  className={STEP}
                >
                  <Minus aria-hidden className="size-4" />
                </button>
              </form>
              <output
                aria-label="Quantidade"
                aria-live="polite"
                className="w-6 text-center font-mono tabular-nums"
              >
                {item.quantity}
              </output>
              <form action={updateQuantity}>
                {lineFields}
                <input type="hidden" name="quantity" value={item.quantity + 1} />
                <button
                  type="submit"
                  aria-label="Aumentar quantidade"
                  disabled={pending || item.quantity >= ceiling}
                  className={STEP}
                >
                  <Plus aria-hidden className="size-4" />
                </button>
              </form>
            </div>
          )}
          <form
            action={removeItem}
            onSubmit={() => {
              removeRequested.current = true;
            }}
          >
            {lineFields}
            <button
              type="submit"
              disabled={pending}
              className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius)] px-2 text-xs font-semibold uppercase tracking-wide text-ks-muted transition-colors duration-[var(--duration-fast)] hover:bg-ks-fg/10 hover:text-ks-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ks-focus disabled:opacity-40"
            >
              <Trash2 aria-hidden className="size-4" />
              Remover
            </button>
          </form>
        </div>
        <p role="status" aria-live="polite" className="text-sm text-red-400">
          {error}
        </p>
      </div>
    </li>
  );
}
