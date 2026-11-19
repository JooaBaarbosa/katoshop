"use server";

import { unwrap } from "@katoshop/api-client";
import { redirect } from "next/navigation";
import { identity } from "../../../lib/api";
import { mergeGuestCart } from "../../../lib/cart";
import { problemToState, secret, text, type FormState } from "../../../lib/form-state";
import { safeNext } from "../../../lib/safe-next";
import { session } from "../../../lib/session";

export async function loginAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const email = text(formData, "email");
  const password = secret(formData, "password");
  const values = { email };

  const fieldErrors: Record<string, string> = {};
  if (!email) fieldErrors.email = "Informe seu email.";
  if (!password) fieldErrors.password = "Informe sua senha.";
  if (Object.keys(fieldErrors).length > 0) return { ok: false, fieldErrors, values };

  let accessToken: string;
  try {
    const pair = unwrap(await identity().POST("/v1/auth/login", { body: { email, password } }));
    await session.setTokens(pair);
    accessToken = pair.access_token;
  } catch (error) {
    return problemToState(error, values);
  }
  // carrinho de visitante vai para a conta; uma falha não impede o login
  await mergeGuestCart(accessToken);
  redirect(safeNext(formData.get("next")));
}
