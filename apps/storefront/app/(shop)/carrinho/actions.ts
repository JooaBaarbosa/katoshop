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
 * Todas têm a assinatura de `useActionState`, para o erro aparecer num role=status também sem
 * JavaScript.
 */

export type LineState = { ok: boolean; message?: string; max?: number } | null;
export type CouponState = { ok: boolean; message?: string; code?: string } | null;
export type ButtonState = { ok: boolean; message?: string } | null;

const PATH = "/carrinho";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const MAX_COUPON_INPUT = 64;
const UPDATE_FAILED = "Não foi possível atualizar o carrinho agora. Tente de novo em instantes.";

type CartCall = Parameters<typeof mutateCart>[0];

function field(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function variantIdOf(formData: FormData): string | undefined {
  const id = field(formData, "variant_id").toLowerCase();
  return UUID.test(id) ? id : undefined;
}

/** As mensagens de `cartErrorMessage` falam de "adicionar"; aqui a falha é de atualização. */
function updateError(error: unknown): { message: string; max?: number } {
  if (
    !(error instanceof ApiProblem) ||
    error.code === "cart.catalog.unavailable" ||
    error.code === "cart.storage.unavailable"
  ) {
    return { message: UPDATE_FAILED };
  }
  return cartErrorMessage(error);
}

/** Uma escrita de linha: erro em pt-BR, mostrado em linha (components/cart-line.tsx). */
async function lineWrite(call: CartCall): Promise<LineState> {
  try {
    await mutateCart(call);
  } catch (error) {
    revalidatePath(PATH);
    return { ok: false, ...updateError(error) };
  }
  revalidatePath(PATH);
  return { ok: true };
}

/** Uma escrita de botão (sem campos): `{ok:false, message}` para o role=status do formulário. */
async function buttonWrite(call: CartCall): Promise<ButtonState> {
  try {
    await mutateCart(call);
  } catch (error) {
    revalidatePath(PATH);
    return { ok: false, message: updateError(error).message };
  }
  revalidatePath(PATH);
  return { ok: true };
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
    return { ok: false, message: `Escolha uma quantidade de 1 a ${MAX_QUANTITY_PER_ITEM}.` };
  }
  return lineWrite((headers, signal) =>
    cart().PATCH("/v1/cart/items/{variant_id}", {
      params: { path: { variant_id: variantId } },
      body: { quantity },
      headers,
      signal,
    }),
  );
}

export async function removeItemAction(_prev: LineState, formData: FormData): Promise<LineState> {
  const variantId = variantIdOf(formData);
  if (!variantId) return { ok: false, message: UPDATE_FAILED };
  return lineWrite((headers, signal) =>
    cart().DELETE("/v1/cart/items/{variant_id}", {
      params: { path: { variant_id: variantId } },
      headers,
      signal,
    }),
  );
}

/** "Limpar indisponíveis". */
export async function removeUnavailableAction(): Promise<ButtonState> {
  return buttonWrite((headers, signal) =>
    cart().DELETE("/v1/cart/items/unavailable", { headers, signal }),
  );
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
    return { ok: false, code, message: updateError(error).message };
  }
  revalidatePath(PATH);
  return { ok: true };
}

export async function removeCouponAction(): Promise<ButtonState> {
  return buttonWrite((headers, signal) => cart().DELETE("/v1/cart/coupon", { headers, signal }));
}

/**
 * "Entendi": limpa os avisos dos itens e o aviso do merge do login (`ks_cart_flash`). O flash
 * só é apagado aqui, numa action (R18), mesmo se o cart falhar; e expira sozinho em 120 s.
 */
export async function ackNoticesAction(): Promise<ButtonState> {
  (await cookies()).delete(CART_FLASH_COOKIE);
  return buttonWrite((headers, signal) => cart().POST("/v1/cart/notices/ack", { headers, signal }));
}
