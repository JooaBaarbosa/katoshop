"use client";

import { Button } from "@katoshop/ui/button";
import { useActionState } from "react";
import { applyCouponAction } from "../app/(shop)/carrinho/actions";

/** Campo de cupom. Numa recusa o código digitado volta no campo, com o motivo em pt-BR. */
export function CouponForm() {
  const [state, action, pending] = useActionState(applyCouponAction, null);
  const error = state && !state.ok ? state.message : undefined;
  return (
    <form action={action} className="space-y-2">
      <label htmlFor="coupon-code" className="text-xs font-semibold uppercase tracking-wide">
        Cupom
      </label>
      <div className="flex gap-2">
        <input
          id="coupon-code"
          name="code"
          defaultValue={state?.code ?? ""}
          maxLength={64}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          aria-describedby="coupon-status"
          className="h-10 min-w-0 flex-1 rounded-[var(--radius)] border border-ks-border bg-ks-surface px-3 font-mono text-sm uppercase text-ks-fg placeholder:normal-case placeholder:text-ks-muted"
          placeholder="Código do cupom"
        />
        <Button type="submit" variant="secondary" disabled={pending}>
          {pending ? "Aplicando..." : "Aplicar"}
        </Button>
      </div>
      <p id="coupon-status" role="status" aria-live="polite" className="text-sm text-red-400">
        {error}
      </p>
    </form>
  );
}
