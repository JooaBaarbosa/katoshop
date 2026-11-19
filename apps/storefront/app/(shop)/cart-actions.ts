"use server";

import { refresh, revalidatePath } from "next/cache";
import { cart } from "../../lib/api";
import { cartErrorMessage, mutateCart } from "../../lib/cart";

export type AddToCartState = { ok: boolean; message?: string; max?: number } | null;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// Teto só contra lixo; o limite real por item (e o estoque) quem decide é o cart.
const MAX_QUANTITY = 1000;

function field(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
}

/**
 * "Adicionar ao carrinho" da página de produto. Server Action é endpoint público: o id e a
 * quantidade são revalidados aqui. Visitante novo ganha o cookie `ks_cart` (lib/cart.ts).
 */
export async function addToCartAction(
  _prev: AddToCartState,
  formData: FormData,
): Promise<AddToCartState> {
  const variantId = field(formData, "variant_id").toLowerCase();
  const rawQuantity = field(formData, "quantity");
  const quantity = /^\d{1,4}$/.test(rawQuantity) ? Number(rawQuantity) : NaN;
  if (!UUID.test(variantId)) return { ok: false, message: "Escolha a cor e o tamanho." };
  if (!(quantity >= 1 && quantity <= MAX_QUANTITY)) {
    return { ok: false, message: "Escolha uma quantidade válida." };
  }

  try {
    await mutateCart((headers, signal) =>
      cart().POST("/v1/cart/items", {
        body: { variant_id: variantId, quantity },
        headers,
        signal,
      }),
    );
  } catch (error) {
    return { ok: false, ...cartErrorMessage(error) };
  }
  revalidatePath("/carrinho");
  // re-renderiza a página atual: o contador do cabeçalho já volta atualizado
  refresh();
  return { ok: true };
}
