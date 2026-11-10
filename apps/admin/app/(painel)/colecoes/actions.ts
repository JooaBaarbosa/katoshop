"use server";

import { unwrap } from "@katoshop/api-client";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  failureResult,
  failureState,
  field,
  optional,
  type ActionResult,
  type ActionState,
} from "../../../lib/action-state";
import { catalog } from "../../../lib/api";
import { staffAction } from "../../../lib/staff-action";

const FIELD_BY_CODE = {
  "catalog.collection.slug_taken": "slug",
  "catalog.collection.invalid_slug": "slug",
};

/** Cria (sem `id`, abre a página da coleção) ou edita (com `id`) uma coleção. */
export async function saveCollectionAction(
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

  const body = {
    name,
    slug: optional(formData, "slug"),
    description: optional(formData, "description"),
    featured: formData.get("featured") === "on",
    position,
  };
  const result = await staffAction(async (token) => {
    const api = catalog(token);
    return id
      ? unwrap(
          await api.PATCH("/v1/admin/collections/{collection_id}", {
            params: { path: { collection_id: id } },
            body,
          }),
        )
      : unwrap(await api.POST("/v1/admin/collections", { body }));
  });
  if (!result.ok) return failureState(result, FIELD_BY_CODE);
  if (!id) redirect(`/colecoes/${result.data.id}`);
  revalidatePath(`/colecoes/${id}`);
  return { ok: true, message: "Coleção atualizada." };
}

export async function deleteCollectionAction(id: string): Promise<ActionResult> {
  const result = await staffAction(async (token) => {
    const { response, error } = await catalog(token).DELETE(
      "/v1/admin/collections/{collection_id}",
      { params: { path: { collection_id: id } } },
    );
    if (!response.ok) unwrap({ error, response });
  });
  if (!result.ok) return failureResult(result);
  revalidatePath("/colecoes");
  return { ok: true };
}

/** Grava a lista completa de produtos da coleção, na ordem de exibição. */
export async function setCollectionProductsAction(
  id: string,
  productIds: string[],
): Promise<ActionResult> {
  const result = await staffAction(async (token) =>
    unwrap(
      await catalog(token).PUT("/v1/admin/collections/{collection_id}/products", {
        params: { path: { collection_id: id } },
        body: { product_ids: productIds },
      }),
    ),
  );
  if (!result.ok) return failureResult(result);
  revalidatePath(`/colecoes/${id}`);
  return { ok: true };
}
