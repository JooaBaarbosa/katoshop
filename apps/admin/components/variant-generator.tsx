"use client";

import { Button } from "@katoshop/ui/button";
import { Checkbox } from "@katoshop/ui/checkbox";
import { useActionState } from "react";
import { generateVariantsAction } from "../app/(painel)/produtos/[id]/actions";
import { COLORS, SIZES } from "../lib/catalog-input";
import { FormError, FormNotice } from "./form-field";

function Option({ name, value, label }: { name: string; value: string; label: string }) {
  const id = `gerar-${name}-${value}`;
  return (
    <div className="flex items-center gap-2">
      <Checkbox id={id} name={name} value={value} />
      <label htmlFor={id} className="text-sm">
        {label}
      </label>
    </div>
  );
}

/** Multisseleção de cores e tamanhos; a API cria só as combinações que faltam. */
export function VariantGenerator({ productId }: { productId: string }) {
  const [state, action, pending] = useActionState(generateVariantsAction, null);
  return (
    <form action={action} className="space-y-4 border border-ks-border bg-ks-surface p-4">
      <input type="hidden" name="product_id" value={productId} />
      <h3 className="text-lg">Gerar grade</h3>
      <FormError message={state?.ok === false ? state.formError : undefined} />
      <FormNotice message={state?.ok ? state.message : undefined} />
      <div className="grid gap-6 sm:grid-cols-2">
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-semibold">Cores</legend>
          {COLORS.map((color) => (
            <Option key={color.code} name="colors" value={color.code} label={color.name} />
          ))}
        </fieldset>
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-semibold">Tamanhos</legend>
          {SIZES.map((size) => (
            <Option key={size} name="sizes" value={size} label={size} />
          ))}
        </fieldset>
      </div>
      <Button type="submit" variant="secondary" disabled={pending}>
        {pending ? "Gerando..." : "Gerar variantes"}
      </Button>
    </form>
  );
}
