"use server";

import { ApiProblem, unwrap } from "@katoshop/api-client";
import { redirect } from "next/navigation";
import { identity } from "../../../lib/api";
import { problemToState, text, type FormState } from "../../../lib/form-state";
import { getRefreshToken, session } from "../../../lib/session";

export async function updateProfileAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const name = text(formData, "name");
  const values = { name };
  if (!name) return { ok: false, fieldErrors: { name: "Informe seu nome." }, values };

  try {
    // Server Action: cookies graváveis, então um 401 pode renovar uma vez (R18)
    await session.withAuth(
      async (token) => unwrap(await identity(token).PATCH("/v1/me", { body: { name } })),
      { refresh: true },
    );
  } catch (error) {
    if (error instanceof ApiProblem && error.status === 401) redirect("/entrar?next=/conta");
    return problemToState(error, values);
  }
  redirect("/conta");
}

export async function logoutAction(): Promise<void> {
  const refreshToken = await getRefreshToken();
  if (refreshToken) {
    try {
      await identity().POST("/v1/auth/logout", { body: { refresh_token: refreshToken } });
    } catch {
      // a sessão local é encerrada mesmo se o identity estiver fora
    }
  }
  await session.clear();
  redirect("/");
}
