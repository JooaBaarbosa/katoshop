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
import { couponFieldErrors, onlyKnown, parseCouponForm, type CouponFields } from "../../../lib/coupons";
import { staffAction, type Failure } from "../../../lib/staff-action";

const FIELD_BY_CODE = {
  "promotions.coupon.code_taken": "code",
  "promotions.coupon.code_immutable": "code",
};

type CatalogClient = ReturnType<typeof catalog>;

/** Categorias e coleções que existem agora no catalog: slugs de fora são descartados. */
async function knownSlugs<T extends Pick<CouponFields, "category_slugs" | "collection_slugs">>(
  api: CatalogClient,
  body: T,
): Promise<T> {
  const wantsCategories = body.category_slugs.length > 0;
  const wantsCollections = body.collection_slugs.length > 0;
  const [categories, collections] = await Promise.all([
    wantsCategories ? api.GET("/v1/admin/categories").then((r) => unwrap(r).items) : [],
    wantsCollections ? api.GET("/v1/admin/collections").then((r) => unwrap(r).items) : [],
  ]);
  return {
    ...body,
    category_slugs: onlyKnown(
      body.category_slugs,
      categories.map((category) => category.slug),
    ),
    collection_slugs: onlyKnown(
      body.collection_slugs,
      collections.map((collection) => collection.slug),
    ),
  };
}

/** Falha da API em estado de formulário; erros do 422 do servidor vão para os campos. */
function couponFailure(failure: Failure): ActionState {
  const fieldErrors = couponFieldErrors(failure.fieldErrors);
  const mapped: Failure = {
    ok: false,
    error: failure.error,
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
  const result = await staffAction(async (token) => {
    const body = await knownSlugs(catalog(token), parsed.body);
    return unwrap(await promotions(token).POST("/v1/admin/coupons", { body }));
  });
  if (!result.ok) return couponFailure(result);
  revalidatePath("/cupons");
  redirect("/cupons?aviso=criado");
}

/** PATCH com a versão lida; código e ativo nunca vão no corpo (código é imutável, extra=forbid). */
export async function updateCouponAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const id = field(formData, "id");
  const version = Number(field(formData, "version"));
  const parsed = parseCouponForm(formData, { mode: "update" });
  if (!parsed.ok) return { ok: false, fieldErrors: parsed.fieldErrors };
  const result = await staffAction(async (token) => {
    const fields = await knownSlugs(catalog(token), parsed.body);
    return unwrap(
      await promotions(token).PATCH("/v1/admin/coupons/{coupon_id}", {
        params: { path: { coupon_id: id } },
        body: { version, ...fields },
      }),
    );
  });
  if (!result.ok) return couponFailure(result);
  revalidatePath("/cupons");
  revalidatePath(`/cupons/${id}`);
  redirect("/cupons?aviso=salvo");
}

async function setActive(id: string, active: boolean): Promise<ActionResult> {
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
