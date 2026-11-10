"use server";

import { unwrap } from "@katoshop/api-client";
import { revalidatePath } from "next/cache";
import {
  failureResult,
  failureState,
  field,
  optional,
  slugPatch,
  type ActionResult,
  type ActionState,
} from "../../../lib/action-state";
import { catalog } from "../../../lib/api";
import { staffAction } from "../../../lib/staff-action";

const FIELD_BY_CODE = {
  "catalog.category.slug_taken": "slug",
  "catalog.category.invalid_slug": "slug",
  "catalog.category.parent_cycle": "parent_id",
};

/** "none" é o valor do item "Nenhuma" no seletor (Radix Select não aceita valor vazio). */
function parentOf(formData: FormData): string | null {
  const value = field(formData, "parent_id");
  return value === "" || value === "none" ? null : value;
}

/** Cria (sem `id`) ou edita (com `id`) uma categoria. */
export async function saveCategoryAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const id = field(formData, "id");
  const name = field(formData, "name");
  const position = Number(field(formData, "position") || "0");
  const fieldErrors: Record<string, string> = {};
  if (!name) fieldErrors.name = "Informe o nome.";
  if (!Number.isInteger(position) || position < 0) {
    fieldErrors.position = "Use um número inteiro a partir de 0.";
  }
  if (Object.keys(fieldErrors).length > 0) return { ok: false, fieldErrors };

  const parentId = parentOf(formData);
  if (id && parentId === id) {
    return {
      ok: false,
      fieldErrors: { parent_id: "Uma categoria não pode ficar dentro dela mesma." },
    };
  }
  const body = { name, parent_id: parentId, position };
  const result = await staffAction(async (token) => {
    const api = catalog(token);
    return id
      ? unwrap(
          await api.PATCH("/v1/admin/categories/{category_id}", {
            params: { path: { category_id: id } },
            // slug vazio na edição: mantém o atual (null não é aceito no PATCH)
            body: { name, ...slugPatch(formData), parent_id: parentId, position },
          }),
        )
      : unwrap(
          await api.POST("/v1/admin/categories", {
            body: { ...body, slug: optional(formData, "slug") },
          }),
        );
  });
  if (!result.ok) return failureState(result, FIELD_BY_CODE);
  revalidatePath("/categorias");
  return { ok: true, message: id ? "Categoria atualizada." : "Categoria criada." };
}

export async function deleteCategoryAction(id: string): Promise<ActionResult> {
  const result = await staffAction(async (token) => {
    const { response, error } = await catalog(token).DELETE(
      "/v1/admin/categories/{category_id}",
      { params: { path: { category_id: id } } },
    );
    if (!response.ok) unwrap({ error, response });
  });
  if (!result.ok) return failureResult(result);
  revalidatePath("/categorias");
  return { ok: true };
}
