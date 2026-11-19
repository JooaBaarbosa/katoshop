import "server-only";
import { ApiProblem, type CartComponents, unwrap } from "@katoshop/api-client";
import { cookies } from "next/headers";
import { cache } from "react";
import { cart } from "./api";
import { GENERIC_ERROR } from "./form-state";
import { getRefreshToken, session, sessionOptions } from "./session";

export type CartOut = CartComponents["schemas"]["CartOut"];
export type CartItem = CartComponents["schemas"]["ItemOut"];
/** Carrinho para a página; `unavailable` quando o serviço não respondeu (mostra vazio). */
export type CartView = CartOut & { unavailable: boolean };

/** ID opaco do carrinho de visitante (UUIDv4). O carrinho de cliente vem do token. */
export const CART_COOKIE = "ks_cart";
/** Aviso de uma leitura para o /carrinho: o merge do login ajustou ou tirou itens. */
export const CART_FLASH_COOKIE = "ks_cart_flash";
export const CART_FLASH_MERGE_ADJUSTED = "merge_adjusted";

const CART_COOKIE_MAX_AGE_SECONDS = 2_592_000; // 30 dias, como o TTL do carrinho de visitante
const CART_FLASH_MAX_AGE_SECONDS = 120;
/** Leitura do cabeçalho: um cart travado não pode segurar toda página da loja. */
const READ_TIMEOUT_MS = 2000;
/** Escrita: o cart consulta o catalog e pode renovar o token de serviço antes de responder. */
const WRITE_TIMEOUT_MS = 5000;

// Texto canônico (minúsculo, com hífens) de um UUIDv4, a única forma que o cart aceita como
// visitante (Ruling S8). Outro valor no cookie nem chega ao cart.
const GUEST_CART_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export const CART_MESSAGES = {
  catalogUnavailable: "Não foi possível adicionar agora. Tente de novo em instantes.",
  itemUnavailable: "Esse item não está mais disponível.",
  sessionExpired: "Sua sessão expirou. Entre de novo para continuar.",
  concurrent: "Seu carrinho mudou em outra aba. Tente de novo.",
  rateLimited: "Muitas tentativas. Aguarde um instante e tente de novo.",
} as const;

type Headers = Record<string, string>;
type CartResult<T> = { data?: T; error?: unknown; response: Response };

export function isGuestCartId(value: unknown): value is string {
  return typeof value === "string" && GUEST_CART_ID.test(value);
}

function baseCookie() {
  return { httpOnly: true, sameSite: "lax", path: "/", secure: sessionOptions().secure } as const;
}

function bearer(token: string): Headers {
  return { Authorization: `Bearer ${token}` };
}

function guestHeaders(cartId: string | undefined): Headers {
  return cartId ? { "X-Cart-Id": cartId } : {};
}

/** Log sem cookies nem ids: só o evento e o erro do cart. */
function logCartFailure(event: string, error: unknown): void {
  console.warn(
    JSON.stringify({
      level: "warn",
      event,
      ...(error instanceof ApiProblem
        ? { status: error.status, code: error.code, trace_id: error.traceId ?? null }
        : { error: error instanceof Error ? error.name : String(error) }),
    }),
  );
}

/** Cliente logado: há access token ou ao menos o refresh token (o proxy ou a action renovam). */
async function signedIn(): Promise<boolean> {
  return (await session.getAccessToken()) !== null || (await getRefreshToken()) !== undefined;
}

/** O ID do cookie, só se tiver o formato de visitante. */
async function guestCartId(): Promise<string | undefined> {
  const value = (await cookies()).get(CART_COOKIE)?.value;
  return isGuestCartId(value) ? value : undefined;
}

/** Cabeçalhos de identidade para o cart: Bearer com sessão, senão o `X-Cart-Id` do cookie. */
export async function cartHeaders(): Promise<HeadersInit> {
  const token = await session.getAccessToken();
  if (token !== null) return bearer(token);
  return guestHeaders(await guestCartId());
}

function emptyCart(unavailable: boolean): CartView {
  return {
    cart_id: null,
    items: [],
    subtotal_cents: 0,
    discount_cents: 0,
    total_cents: 0,
    coupon: null,
    checkout_blocked: false,
    unavailable,
  };
}

async function readCart(headers: Headers): Promise<CartOut> {
  return unwrap(
    await cart().GET("/v1/cart", { headers, signal: AbortSignal.timeout(READ_TIMEOUT_MS) }),
  );
}

/**
 * Carrinho atual, só leitura (seguro em Server Components): `withAuth` sem refresh (R18) e
 * nenhum cookie é alterado. Qualquer falha vira carrinho vazio com `unavailable: true`.
 * Uma busca por requisição (cabeçalho e página compartilham).
 */
export const getCart = cache(async (): Promise<CartView> => {
  try {
    if (await signedIn()) {
      const data = await session.withAuth((token) => readCart(bearer(token)));
      return { ...data, unavailable: false };
    }
    const cartId = await guestCartId();
    if (!cartId) return emptyCart(false);
    return { ...(await readCart(guestHeaders(cartId))), unavailable: false };
  } catch (error) {
    logCartFailure("cart.read_failed", error);
    return emptyCart(true);
  }
});

/** Unidades no carrinho para o cabeçalho; `null` quando o cart não respondeu. */
export async function cartCount(): Promise<number | null> {
  const view = await getCart();
  if (view.unavailable) return null;
  return view.items.reduce((total, item) => total + item.quantity, 0);
}

/**
 * Executa uma escrita no cart com a identidade atual. Só em Server Actions: renova a sessão
 * (`withAuth` com refresh) e mantém o `ks_cart` do visitante:
 * - grava o cookie quando o cart devolve um `cart_id` novo (primeiro item, ou o antigo expirou);
 * - apaga o cookie malformado, recusado pelo cart (`invalid_id`) ou de um carrinho que sumiu.
 */
export async function mutateCart<T extends CartOut>(
  call: (headers: Headers, signal: AbortSignal) => Promise<CartResult<T>>,
): Promise<T> {
  const signal = () => AbortSignal.timeout(WRITE_TIMEOUT_MS);
  if (await signedIn()) {
    return session.withAuth(async (token) => unwrap(await call(bearer(token), signal())), {
      refresh: true,
    });
  }

  const store = await cookies();
  const raw = store.get(CART_COOKIE)?.value;
  const cartId = isGuestCartId(raw) ? raw : undefined;
  if (raw !== undefined && cartId === undefined) store.delete(CART_COOKIE);

  let data: T;
  try {
    data = unwrap(await call(guestHeaders(cartId), signal()));
  } catch (error) {
    if (cartId && error instanceof ApiProblem && error.code === "cart.cart.invalid_id") {
      store.delete(CART_COOKIE);
    }
    throw error;
  }
  if (data.cart_id !== null && data.cart_id !== cartId && isGuestCartId(data.cart_id)) {
    store.set(CART_COOKIE, data.cart_id, {
      ...baseCookie(),
      maxAge: CART_COOKIE_MAX_AGE_SECONDS,
    });
  } else if (cartId && data.cart_id === null) {
    store.delete(CART_COOKIE);
  }
  return data;
}

/** Mensagem pt-BR para uma falha de escrita no carrinho; `max` quando o cart informa o teto. */
export function cartErrorMessage(error: unknown): { message: string; max?: number } {
  if (!(error instanceof ApiProblem)) return { message: CART_MESSAGES.catalogUnavailable };
  const max = typeof error.extras.max === "number" ? error.extras.max : undefined;
  switch (error.code) {
    case "cart.item.quantity_exceeds_stock":
      if (max === undefined) return { message: "Não temos essa quantidade desse tamanho." };
      if (max <= 0) return { message: "Esse tamanho acabou de esgotar.", max };
      return {
        message: `Só temos ${max} ${max === 1 ? "unidade" : "unidades"} desse tamanho.`,
        max,
      };
    case "cart.item.quantity_limit":
      return max === undefined
        ? { message: "Quantidade acima do limite por item." }
        : { message: `Você pode levar até ${max} unidades de cada item.`, max };
    case "cart.cart.too_many_lines":
      return max === undefined
        ? { message: "Seu carrinho chegou ao limite de itens diferentes." }
        : { message: `Seu carrinho chegou ao limite de ${max} itens diferentes.`, max };
    case "cart.item.unavailable":
    case "cart.item.not_found":
      return { message: CART_MESSAGES.itemUnavailable };
    case "cart.catalog.unavailable":
    case "cart.storage.unavailable":
      return { message: CART_MESSAGES.catalogUnavailable };
    case "cart.cart.concurrent_update":
      return { message: CART_MESSAGES.concurrent };
  }
  if (error.status === 401) return { message: CART_MESSAGES.sessionExpired };
  if (error.status === 429) return { message: CART_MESSAGES.rateLimited };
  return { message: GENERIC_ERROR };
}

/**
 * Depois do login ou do cadastro (cookies graváveis): une o carrinho de visitante ao da conta
 * com o token recém-emitido e apaga o `ks_cart`. Nunca lança: uma falha só é logada, e o cookie
 * fica para a próxima tentativa. Itens ajustados ou retirados deixam um aviso curto para o
 * /carrinho.
 */
export async function mergeGuestCart(accessToken: string): Promise<void> {
  try {
    const store = await cookies();
    const raw = store.get(CART_COOKIE)?.value;
    if (raw === undefined) return;
    if (!isGuestCartId(raw)) {
      store.delete(CART_COOKIE);
      return;
    }
    const merged = unwrap(
      await cart(accessToken).POST("/v1/cart/merge", {
        body: { guest_cart_id: raw },
        signal: AbortSignal.timeout(WRITE_TIMEOUT_MS),
      }),
    );
    store.delete(CART_COOKIE);
    const { reduced, dropped } = merged.merge_report;
    if (reduced.length > 0 || dropped.length > 0) {
      store.set(CART_FLASH_COOKIE, CART_FLASH_MERGE_ADJUSTED, {
        ...baseCookie(),
        maxAge: CART_FLASH_MAX_AGE_SECONDS,
      });
    }
  } catch (error) {
    logCartFailure("cart.merge_failed", error);
  }
}
