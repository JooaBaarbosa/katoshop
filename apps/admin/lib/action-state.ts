import type { Failure } from "./staff-action";

/** Estado das actions de formulário (useActionState). */
export type ActionState =
  | { ok: true; message: string }
  | {
      ok: false;
      formError?: string;
      fieldErrors?: Record<string, string>;
      code?: string;
    }
  | null;

/** Resultado das actions chamadas direto de componentes (sem formulário). */
export type ActionResult = { ok: true } | { ok: false; error: string; code?: string };

/**
 * Falha da API em estado de formulário. Códigos ligados a um campo (ex.: endereço repetido)
 * aparecem nele; o resto vira erro do formulário.
 */
export function failureState(failure: Failure, fieldByCode: Record<string, string> = {}) {
  const field = failure.code ? fieldByCode[failure.code] : undefined;
  if (field) {
    return {
      ok: false as const,
      code: failure.code,
      fieldErrors: { [field]: failure.error },
    };
  }
  return {
    ok: false as const,
    formError: failure.error,
    ...(failure.code ? { code: failure.code } : {}),
    ...(failure.fieldErrors ? { fieldErrors: failure.fieldErrors } : {}),
  };
}

export function failureResult(failure: Failure): ActionResult {
  return { ok: false, error: failure.error, ...(failure.code ? { code: failure.code } : {}) };
}

export function field(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
}

/** Campo opcional: vazio vira null (a API gera o slug, limpa a descrição etc.). */
export function optional(formData: FormData, name: string): string | null {
  return field(formData, name) || null;
}
