"use client";

import { Button } from "@katoshop/ui/button";
import { useActionState } from "react";
import { FormError, FormField } from "../../../components/form-field";
import { updateProfileAction } from "./actions";

export function ProfileForm({ name }: { name: string }) {
  const [state, action, pending] = useActionState(updateProfileAction, null);
  return (
    <form action={action} className="space-y-5" noValidate>
      <FormError message={state?.formError} />
      <FormField
        name="name"
        label="Nome"
        autoComplete="name"
        required
        maxLength={120}
        defaultValue={state?.values?.name ?? name}
        error={state?.fieldErrors?.name}
      />
      <Button type="submit" variant="secondary" disabled={pending}>
        {pending ? "Salvando..." : "Salvar"}
      </Button>
    </form>
  );
}
