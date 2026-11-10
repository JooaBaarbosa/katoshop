"use server";

import { unwrap } from "@katoshop/api-client";
import { revalidatePath } from "next/cache";
import { failureState, field, optional, type ActionState } from "../../../../../../../lib/action-state";
import { catalog } from "../../../../../../../lib/api";
import { parseDelta, STOCK_REASONS } from "../../../../../../../lib/catalog-input";
import { staffAction } from "../../../../../../../lib/staff-action";

const REASONS = new Set<string>(STOCK_REASONS.map((reason) => reason.value));

export async function adjustStockAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const productId = field(formData, "product_id");
  const variantId = field(formData, "variant_id");
  const delta = parseDelta(field(formData, "delta"));
  const reason = field(formData, "reason");
  const fieldErrors: Record<string, string> = {};
  if (delta === null) fieldErrors.delta = "Informe um número inteiro diferente de zero.";
  if (!REASONS.has(reason)) fieldErrors.reason = "Escolha um motivo.";
  if (Object.keys(fieldErrors).length > 0 || delta === null) return { ok: false, fieldErrors };

  const result = await staffAction(async (token) =>
    unwrap(
      await catalog(token).POST("/v1/admin/variants/{variant_id}/stock-adjustments", {
        params: { path: { variant_id: variantId } },
        body: { delta, reason, note: optional(formData, "note") },
      }),
    ),
  );
  if (!result.ok) return failureState(result);
  revalidatePath(`/produtos/${productId}/variantes/${variantId}/estoque`);
  const { available } = result.data.variant;
  return { ok: true, message: `Ajuste registrado. Disponível agora: ${available}.` };
}
