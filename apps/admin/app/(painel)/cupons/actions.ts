"use server";

import { unwrap } from "@katoshop/api-client";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  failureResult,
  failureState,
  field,
  type ActionResult,
  type ActionState,
} from "../../../lib/action-state";
import { catalog, promotions } from "../../../lib/api";
import {
  couponFieldErrors,
  hasRootError,
  isCouponId,
  MESSAGES,
  parseCouponForm,
  slugErrors,
} from "../../../lib/coupons";
import { messageFor } from "../../../lib/problem-messages";
import { staffAction, type Failure } from "../../../lib/staff-action";

const FIELD_BY_CODE = {
  "promotions.coupon.code_taken": "code",
  "promotions.coupon.code_immutable": "code",
};

const NOT_FOUND = messageFor("promotions.coupon.not_found");

type SlugLists = { category_slugs: readonly string[]; collection_slugs: readonly string[] };
type Invalid = { invalid: Record<string, string> };

/**
 * Confere as categorias e coleções enviadas contra o catalog, lido agora. Na edição, os slugs que
 * o cupom JÁ tem continuam valendo mesmo se sumiram do catálogo (lidos no servidor por `saved`,
 * nunca de campo oculto): uma edição qualquer não pode transformar o cupom em "loja toda".
 * Slug novo fora do catálogo vira erro no campo, nunca é descartado em silêncio.
 */
async function slugCheck(
  token: string,
  body: SlugLists,
  saved?: () => Promise<SlugLists>,
): Promise<Record<string, string>> {
  const api = catalog(token);
  const [categories, collections] = await Promise.all([
    body.category_slugs.length > 0
      ? api.GET("/v1/admin/categories").then((r) => unwrap(r).items.map((c) => c.slug))
      : undefined,
    body.collection_slugs.length > 0
      ? api.GET("/v1/admin/collections").then((r) => unwrap(r).items.map((c) => c.slug))
      : undefined,
  ]);
  const errors = slugErrors(body, {
    ...(categories ? { categories } : {}),
    ...(collections ? { collections } : {}),
  });
  if (Object.keys(errors).length === 0 || !saved) return errors;
  const current = await saved();
  return slugErrors(body, {
    ...(categories ? { categories: [...categories, ...current.category_slugs] } : {}),
    ...(collections ? { collections: [...collections, ...current.collection_slugs] } : {}),
  });
}

function isInvalid(value: unknown): value is Invalid {
  return typeof value === "object" && value !== null && "invalid" in value;
}

/** Falha da API em estado de formulário; erros do 422 do servidor vão para os campos. */
function couponFailure(failure: Failure): ActionState {
  const fieldErrors = couponFieldErrors(failure.fieldErrors);
  const rootOnly = !fieldErrors && hasRootError(failure.fieldErrors);
  const mapped: Failure = {
    ok: false,
    error: rootOnly ? MESSAGES.cross_fields : failure.error,
    ...(failure.code ? { code: failure.code } : {}),
    ...(fieldErrors ? { fieldErrors } : {}),
  };
  return failureState(mapped, FIELD_BY_CODE);
}

export async function createCouponAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const parsed = parseCouponForm(formData);
  if (!parsed.ok) return { ok: false, fieldErrors: parsed.fieldErrors };
  const result = await staffAction(async (token): Promise<Invalid | { id: string }> => {
    const invalid = await slugCheck(token, parsed.body);
    if (Object.keys(invalid).length > 0) return { invalid };
    return unwrap(await promotions(token).POST("/v1/admin/coupons", { body: parsed.body }));
  });
  if (!result.ok) return couponFailure(result);
  if (isInvalid(result.data)) return { ok: false, fieldErrors: result.data.invalid };
  revalidatePath("/cupons");
  redirect("/cupons?aviso=criado");
}

/** PATCH com a versão lida; código e ativo nunca vão no corpo (código é imutável, extra=forbid). */
export async function updateCouponAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const id = field(formData, "id");
  if (!isCouponId(id)) return { ok: false, formError: NOT_FOUND };
  const version = Number(field(formData, "version"));
  const parsed = parseCouponForm(formData, { mode: "update" });
  if (!parsed.ok) return { ok: false, fieldErrors: parsed.fieldErrors };
  const result = await staffAction(async (token): Promise<Invalid | { id: string }> => {
    const api = promotions(token);
    const invalid = await slugCheck(token, parsed.body, async () =>
      unwrap(
        await api.GET("/v1/admin/coupons/{coupon_id}", { params: { path: { coupon_id: id } } }),
      ),
    );
    if (Object.keys(invalid).length > 0) return { invalid };
    return unwrap(
      await api.PATCH("/v1/admin/coupons/{coupon_id}", {
        params: { path: { coupon_id: id } },
        body: { version, ...parsed.body },
      }),
    );
  });
  if (!result.ok) return couponFailure(result);
  if (isInvalid(result.data)) return { ok: false, fieldErrors: result.data.invalid };
  revalidatePath("/cupons");
  revalidatePath(`/cupons/${id}`);
  redirect("/cupons?aviso=salvo");
}

async function setActive(id: string, active: boolean): Promise<ActionResult> {
  if (!isCouponId(id)) return { ok: false, error: NOT_FOUND };
  const path = active
    ? "/v1/admin/coupons/{coupon_id}/activate"
    : "/v1/admin/coupons/{coupon_id}/deactivate";
  const result = await staffAction(async (token) =>
    unwrap(await promotions(token).POST(path, { params: { path: { coupon_id: id } } })),
  );
  if (!result.ok) return failureResult(result);
  revalidatePath("/cupons");
  revalidatePath(`/cupons/${id}`);
  return { ok: true };
}

export async function activateCouponAction(id: string): Promise<ActionResult> {
  return setActive(id, true);
}

export async function deactivateCouponAction(id: string): Promise<ActionResult> {
  return setActive(id, false);
}

export async function deleteCouponAction(id: string): Promise<ActionResult> {
  if (!isCouponId(id)) return { ok: false, error: NOT_FOUND };
  const result = await staffAction(async (token) => {
    const { response, error } = await promotions(token).DELETE("/v1/admin/coupons/{coupon_id}", {
      params: { path: { coupon_id: id } },
    });
    if (!response.ok) unwrap({ error, response });
  });
  if (!result.ok) return failureResult(result);
  revalidatePath("/cupons");
  return { ok: true };
}
