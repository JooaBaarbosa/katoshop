"use client";

import { Button } from "@katoshop/ui/button";
import { RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useActionState, useTransition } from "react";
import {
  createProductAction,
  updateProductAction,
} from "../app/(painel)/produtos/[id]/actions";
import type { ActionState } from "../lib/action-state";
import type { AdminProduct, Category } from "../lib/catalog-data";
import { formatAttributes, formatCentsInput } from "../lib/catalog-input";
import { FormError, FormField, FormNotice, TextareaField } from "./form-field";
import { SelectField } from "./select-field";

const CONFLICT = "catalog.product.version_conflict";

type EditState = (ActionState & { submittedVersion?: number }) | null;

/** Dados do produto. Na edição, a versão lida vai oculta e o 409 oferece "Recarregar". */
export function ProductForm({
  product,
  categories,
}: {
  product?: AdminProduct;
  categories: Category[];
}) {
  const router = useRouter();
  const [reloading, startReload] = useTransition();
  const [state, action, pending] = useActionState<EditState, FormData>(
    async (prev, formData) => {
      const submittedVersion = Number(formData.get("version"));
      const result = product
        ? await updateProductAction(prev, formData)
        : await createProductAction(prev, formData);
      return result && { ...result, submittedVersion };
    },
    null,
  );

  const failed = state?.ok === false ? state : null;
  // depois de recarregar, a versão nova chega pelas props e o aviso some
  const conflict =
    failed?.code === CONFLICT && product !== undefined && state?.submittedVersion === product.version;
  const errors = failed?.fieldErrors ?? {};

  return (
    <form action={action} className="max-w-2xl space-y-5" noValidate>
      {conflict ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 border border-red-700 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          <p>{failed?.formError}</p>
          <Button
            type="button"
            variant="secondary"
            disabled={reloading}
            onClick={() => startReload(() => router.refresh())}
          >
            <RefreshCw aria-hidden className="size-4" />
            {reloading ? "Recarregando..." : "Recarregar"}
          </Button>
        </div>
      ) : (
        <FormError message={failed?.formError} />
      )}
      <FormNotice message={state?.ok ? state.message : undefined} />

      {product && (
        <>
          <input type="hidden" name="id" value={product.id} />
          <input type="hidden" name="version" value={product.version} />
        </>
      )}

      {/* a versão nova (salvo ou recarregado) remonta os campos com os valores atuais */}
      <div key={product?.version ?? "novo"} className="space-y-5">
        <FormField
          name="name"
          label="Nome"
          required
          maxLength={200}
          defaultValue={product?.name}
          error={errors.name}
        />
        <FormField
          name="slug"
          label="Endereço (slug)"
          maxLength={160}
          defaultValue={product?.slug}
          placeholder={product ? undefined : "Vazio: gerado a partir do nome"}
          error={errors.slug}
        />
        <SelectField
          name="category_id"
          label="Categoria"
          required
          defaultValue={product?.category_id}
          options={categories.map((category) => ({ value: category.id, label: category.name }))}
          error={errors.category_id}
        />
        <FormField
          name="base_price"
          label="Preço base (R$)"
          inputMode="decimal"
          required
          placeholder="129,90"
          defaultValue={product ? formatCentsInput(product.base_price_cents) : undefined}
          error={errors.base_price}
        />
        <TextareaField
          name="description"
          label="Descrição"
          rows={5}
          defaultValue={product?.description ?? ""}
          error={errors.description}
        />
        <TextareaField
          name="attributes"
          label="Ficha técnica"
          rows={4}
          hint="Uma linha por item, no formato Nome: valor. Exemplo: Composição: 100% algodão"
          defaultValue={product ? formatAttributes(product.attributes) : ""}
          error={errors.attributes}
        />
      </div>

      <Button type="submit" disabled={pending}>
        {pending ? "Salvando..." : product ? "Salvar alterações" : "Criar produto"}
      </Button>
    </form>
  );
}
