"use client";

import { Button } from "@katoshop/ui/button";
import { type ReactNode, useActionState } from "react";
import type { ButtonState } from "../app/(shop)/carrinho/actions";

/**
 * Botão de uma ação do carrinho sem campos (Entendi, Limpar indisponíveis, Remover cupom).
 * O erro volta pelo `useActionState` e aparece no role=status, também sem JavaScript.
 */
export function CartActionButton({
  action,
  children,
  variant = "secondary",
  className,
}: {
  /** Server Action sem campos, passada direto (sem embrulho) para funcionar sem JavaScript. */
  action: () => Promise<ButtonState>;
  children: ReactNode;
  variant?: "secondary" | "ghost";
  className?: string;
}) {
  const [state, dispatch, pending] = useActionState<ButtonState>(action, null);
  return (
    <form action={dispatch} className="flex flex-col items-end gap-1">
      <Button type="submit" variant={variant} disabled={pending} className={className}>
        {children}
      </Button>
      <p role="status" aria-live="polite" className="text-right text-sm text-red-400">
        {state && !state.ok ? state.message : null}
      </p>
    </form>
  );
}
