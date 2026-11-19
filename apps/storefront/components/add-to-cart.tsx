"use client";

import { Button } from "@katoshop/ui/button";
import { toast } from "@katoshop/ui/toast";
import Link from "next/link";
import { useActionState, useEffect } from "react";
import { addToCartAction } from "../app/(shop)/cart-actions";

/**
 * Botão da página de produto. Sem `variantId` (cor e tamanho ainda não escolhidos, ou esgotado)
 * fica desabilitado. A página remonta o componente por variante (`key`), então uma mensagem de
 * estoque não sobra ao trocar de tamanho.
 */
export function AddToCart({ variantId }: { variantId: string | undefined }) {
  const [state, action, pending] = useActionState(addToCartAction, null);

  useEffect(() => {
    if (state?.ok) {
      toast.success("Adicionado ao carrinho", {
        description: (
          <Link href="/carrinho" className="font-semibold text-ks-fg underline underline-offset-4">
            Ver carrinho
          </Link>
        ),
      });
    }
  }, [state]);

  const error = state && !state.ok ? state.message : undefined;
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="variant_id" value={variantId ?? ""} />
      <input type="hidden" name="quantity" value="1" />
      <Button type="submit" size="lg" className="w-full" disabled={!variantId || pending}>
        {pending ? "Adicionando..." : "Adicionar ao carrinho"}
      </Button>
      {!variantId && <p className="text-sm text-ks-muted">Escolha a cor e o tamanho.</p>}
      <p role="status" aria-live="polite" className="text-sm text-red-400">
        {error}
      </p>
    </form>
  );
}
