"use server";

import { ApiProblem } from "@katoshop/api-client";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { cart } from "../../../lib/api";
import { CART_FLASH_COOKIE, cartErrorMessage, mutateCart } from "../../../lib/cart";
import {
  COUPON_UNAVAILABLE,
  MAX_QUANTITY_PER_ITEM,
  messageForCoupon,
} from "../../../lib/cart-messages";

/*
 * Ações do /carrinho. Todas passam por `mutateCart` (lib/cart.ts): com sessão usam
 * `withAuth(..., { refresh: true })` (R18); visitante manda o `X-Cart-Id` do cookie. Sem
 * JavaScript, os formulários postam a action no corpo e o router `storefront-forms` do Traefik
 * aplica o limite por IP (R24). Server Action é endpoint público: toda entrada é revalidada.
 */

export type LineState = { ok: boolean; message?: string; max?: number } | null;
export type CouponState = { ok: boolean; message?: string; code?: string } | null;

const PATH = "/carrinho";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const MAX_COUPON_INPUT = 64;
const UPDATE_FAILED = "Não foi possível atualizar o carrinho agora. Tente de novo em instantes.";

function field(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function variantIdOf(formData: FormData): string | undefined {
  const id = field(formData, "variant_id").toLowerCase();
  return UUID.test(id) ? id : undefined;
}

/** As mensagens de `cartErrorMessage` falam de "adicionar"; aqui a falha é de atualização. */
function lineError(error: unknown): { message: string; max?: number } {
  if (
    !(error instanceof ApiProblem) ||
    error.code === "cart.catalog.unavailable" ||
    error.code === "cart.storage.unavailable"
  ) {
    return { message: UPDATE_FAILED };
  }
  return cartErrorMessage(error);
}

/** Loga a falha sem cookies nem ids (as ações sem estado não têm onde mostrar o erro). */
function logFailure(event: string, error: unknown): void {
  console.warn(
    JSON.stringify({
      level: "warn",
      event,
      ...(error instanceof ApiProblem
        ? { status: error.status, code: error.code }
        : { error: error instanceof Error ? error.name : String(error) }),
    }),
  );
}

export async function updateQuantityAction(
  _prev: LineState,
  formData: FormData,
): Promise<LineState> {
  const variantId = variantIdOf(formData);
  const raw = field(formData, "quantity");
  const quantity = /^\d{1,2}$/.test(raw) ? Number(raw) : NaN;
  if (!variantId) return { ok: false, message: UPDATE_FAILED };
  if (!(quantity >= 1 && quantity <= MAX_QUANTITY_PER_ITEM)) {
    return {
      ok: false,
      message: `Escolha uma quantidade de 1 a ${MAX_QUANTITY_PER_ITEM}.`,
    };
  }

  try {
    await mutateCart((headers, signal) =>
      cart().PATCH("/v1/cart/items/{variant_id}", {
        params: { path: { variant_id: variantId } },
        body: { quantity },
        headers,
        signal,
      }),
    );
  } catch (error) {
    revalidatePath(PATH);
    return { ok: false, ...lineError(error) };
  }
  revalidatePath(PATH);
  return { ok: true };
}

export async function removeItemAction(_prev: LineState, formData: FormData): Promise<LineState> {
  const variantId = variantIdOf(formData);
  if (!variantId) return { ok: false, message: UPDATE_FAILED };

  try {
    await mutateCart((headers, signal) =>
      cart().DELETE("/v1/cart/items/{variant_id}", {
        params: { path: { variant_id: variantId } },
        headers,
        signal,
      }),
    );
  } catch (error) {
    revalidatePath(PATH);
    return { ok: false, ...lineError(error) };
  }
  revalidatePath(PATH);
  return { ok: true };
}

/**
 * "Limpar indisponíveis". Sem estado de formulário: numa falha a página volta a mostrar os
 * itens como estão (ou a página de erro, se o cart estiver fora).
 */
export async function removeUnavailableAction(): Promise<void> {
  try {
    await mutateCart((headers, signal) =>
      cart().DELETE("/v1/cart/items/unavailable", { headers, signal }),
    );
  } catch (error) {
    logFailure("cart.remove_unavailable_failed", error);
  }
  revalidatePath(PATH);
}

export async function applyCouponAction(
  _prev: CouponState,
  formData: FormData,
): Promise<CouponState> {
  // devolve o texto digitado para o campo não se perder numa recusa (também sem JavaScript)
  const code = field(formData, "code").slice(0, MAX_COUPON_INPUT);
  if (code === "") return { ok: false, code, message: "Digite o código do cupom." };

  try {
    await mutateCart((headers, signal) =>
      cart().PUT("/v1/cart/coupon", { body: { code }, headers, signal }),
    );
  } catch (error) {
    revalidatePath(PATH);
    if (error instanceof ApiProblem) {
      if (error.code === "cart.coupon.invalid") {
        const { reason, min_order_cents: min } = error.extras;
        return {
          ok: false,
          code,
          message: messageForCoupon(
            typeof reason === "string" ? reason : null,
            typeof min === "number" ? min : null,
          ),
        };
      }
      if (error.code === "cart.promotions.unavailable") {
        return { ok: false, code, message: COUPON_UNAVAILABLE };
      }
      // formato fora de ^[A-Z0-9-]{3,32}$ chega como request.validation
      if (error.code === "request.validation") {
        return { ok: false, code, message: messageForCoupon("promotions.coupon.not_found") };
      }
    }
    return { ok: false, code, message: lineError(error).message };
  }
  revalidatePath(PATH);
  return { ok: true };
}

export async function removeCouponAction(): Promise<void> {
  try {
    await mutateCart((headers, signal) => cart().DELETE("/v1/cart/coupon", { headers, signal }));
  } catch (error) {
    logFailure("cart.remove_coupon_failed", error);
  }
  revalidatePath(PATH);
}

/**
 * "Entendi": limpa os avisos dos itens e o aviso do merge do login (`ks_cart_flash`). O flash
 * só é apagado aqui, numa action (R18), e expira sozinho em 120 s.
 */
export async function ackNoticesAction(): Promise<void> {
  (await cookies()).delete(CART_FLASH_COOKIE);
  try {
    await mutateCart((headers, signal) => cart().POST("/v1/cart/notices/ack", { headers, signal }));
  } catch (error) {
    logFailure("cart.ack_notices_failed", error);
  }
  revalidatePath(PATH);
}
