"use client";

import { Button } from "@katoshop/ui/button";
import { useActionState } from "react";
import { FormError, FormField } from "../../../components/form-field";
import { loginAction } from "./actions";

export function LoginForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState(loginAction, null);
  return (
    <form action={action} className="space-y-5" noValidate>
      <FormError message={state?.formError} />
      <input type="hidden" name="next" value={next} />
      <FormField
        name="email"
        label="Email"
        type="email"
        autoComplete="email"
        required
        defaultValue={state?.values?.email}
        error={state?.fieldErrors?.email}
      />
      <FormField
        name="password"
        label="Senha"
        type="password"
        autoComplete="current-password"
        required
        error={state?.fieldErrors?.password}
      />
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "Entrando..." : "Entrar"}
      </Button>
    </form>
  );
}
