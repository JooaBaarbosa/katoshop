"use client";

import { Button } from "@katoshop/ui/button";
import { useActionState } from "react";
import { FormError, FormField } from "../../../components/form-field";
import { registerAction } from "./actions";

export function RegisterForm() {
  const [state, action, pending] = useActionState(registerAction, null);
  return (
    <form action={action} className="space-y-5" noValidate>
      <FormError message={state?.formError} />
      <FormField
        name="name"
        label="Nome"
        autoComplete="name"
        required
        maxLength={120}
        defaultValue={state?.values?.name}
        error={state?.fieldErrors?.name}
      />
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
        autoComplete="new-password"
        required
        minLength={10}
        hint="Pelo menos 10 caracteres. Evite senhas comuns e não use seu email."
        error={state?.fieldErrors?.password}
      />
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "Criando..." : "Criar conta"}
      </Button>
    </form>
  );
}
