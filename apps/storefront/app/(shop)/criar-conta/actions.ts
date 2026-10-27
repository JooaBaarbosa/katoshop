"use server";

import { unwrap } from "@katoshop/api-client";
import { redirect } from "next/navigation";
import { identity } from "../../../lib/api";
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

  try {
    const pair = unwrap(
      await identity().POST("/v1/auth/register", { body: { name, email, password } }),
    );
    await session.setTokens(pair);
  } catch (error) {
    return problemToState(error, values);
  }
  redirect("/conta");
}
