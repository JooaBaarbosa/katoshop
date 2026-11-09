"use server";

import { unwrap } from "@katoshop/api-client";
import { redirect } from "next/navigation";
import { identity } from "../../lib/api";
import {
  INVALID_CREDENTIALS,
  problemToState,
  secret,
  text,
  type FormState,
} from "../../lib/form-state";
import { safeNext } from "../../lib/safe-next";
import { session } from "../../lib/session";

export async function loginAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const email = text(formData, "email");
  const password = secret(formData, "password");
  const values = { email };

  const fieldErrors: Record<string, string> = {};
  if (!email) fieldErrors.email = "Informe seu email.";
  if (!password) fieldErrors.password = "Informe sua senha.";
  if (Object.keys(fieldErrors).length > 0) return { ok: false, fieldErrors, values };

  try {
    const pair = unwrap(
      await identity().POST("/v1/auth/staff/login", { body: { email, password } }),
    );
    // o identity já recusa clientes neste endpoint; aqui é só uma segunda trava
    if (pair.user.kind !== "staff") return { ok: false, formError: INVALID_CREDENTIALS, values };
    await session.setTokens(pair);
  } catch (error) {
    return problemToState(error, values);
  }
  redirect(safeNext(formData.get("next"), "/"));
}
