"use client";

import { Button } from "@katoshop/ui/button";
import { useActionState } from "react";
import { adjustStockAction } from "../app/(painel)/produtos/[id]/variantes/[vid]/estoque/actions";
import { STOCK_REASONS } from "../lib/catalog-input";
import { FormError, FormField, FormNotice } from "./form-field";
import { SelectField } from "./select-field";

/** Ajuste manual de estoque: quantidade com sinal, motivo e nota opcional. */
export function StockAdjustForm({ productId, variantId }: { productId: string; variantId: string }) {
  const [state, action, pending] = useActionState(adjustStockAction, null);
  const errors = state?.ok === false ? (state.fieldErrors ?? {}) : {};
  return (
    <form
      action={action}
      className="max-w-xl space-y-4 border border-ks-border bg-ks-surface p-4"
      noValidate
    >
      <h2 className="text-xl">Ajustar estoque</h2>
      <input type="hidden" name="product_id" value={productId} />
      <input type="hidden" name="variant_id" value={variantId} />
      <FormError message={state?.ok === false ? state.formError : undefined} />
      <FormNotice message={state?.ok ? state.message : undefined} />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          name="delta"
          label="Quantidade (use - para retirar)"
          inputMode="numeric"
          required
          placeholder="+10 ou -2"
          error={errors.delta}
        />
        <SelectField
          name="reason"
          label="Motivo"
          required
          defaultValue="adjustment"
          options={STOCK_REASONS.map((reason) => ({ value: reason.value, label: reason.label }))}
          error={errors.reason}
        />
      </div>
      <FormField name="note" label="Nota (opcional)" maxLength={500} error={errors.note} />
      <Button type="submit" disabled={pending}>
        {pending ? "Registrando..." : "Registrar ajuste"}
      </Button>
    </form>
  );
}
