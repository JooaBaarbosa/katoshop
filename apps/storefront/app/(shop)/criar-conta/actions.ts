"use server";

import { unwrap } from "@katoshop/api-client";
import { redirect } from "next/navigation";
import { identity } from "../../../lib/api";
import { mergeGuestCart } from "../../../lib/cart";
import { problemToState, secret, text, type FormState } from "../../../lib/form-state";
import { session } from "../../../lib/session";

export async function registerAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const name = text(formData, "name");
  const email = text(formData, "email");
  const password = secret(formData, "password");
  const values = { name, email };

  const fieldErrors: Record<string, string> = {};
  if (!name) fieldErrors.name = "Informe seu nome.";
  if (!email) fieldErrors.email = "Informe seu email.";
  if (!password) fieldErrors.password = "Crie uma senha.";
  if (Object.keys(fieldErrors).length > 0) return { ok: false, fieldErrors, values };

  let accessToken: string;
  try {
    const pair = unwrap(
      await identity().POST("/v1/auth/register", { body: { name, email, password } }),
    );
    await session.setTokens(pair);
    accessToken = pair.access_token;
  } catch (error) {
    return problemToState(error, values);
  }
  // carrinho de visitante vai para a conta; uma falha não impede o cadastro
  await mergeGuestCart(accessToken);
  redirect("/conta");
}
