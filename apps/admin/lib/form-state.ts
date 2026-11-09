import { ApiProblem } from "@katoshop/api-client";

/** Estado devolvido pelas server actions de formulário (o sucesso faz redirect). */
export type FormState = {
  ok: false;
  fieldErrors?: Record<string, string>;
  formError?: string;
  /** Valores não secretos para reapresentar no formulário após erro. */
  values?: Record<string, string>;
} | null;

export const GENERIC_ERROR = "Não foi possível concluir agora. Tente de novo em instantes.";
export const INVALID_CREDENTIALS = "Email ou senha incorretos.";

/** Converte um erro de chamada à API em estado de formulário com mensagens em pt-BR. */
export function problemToState(error: unknown, values?: Record<string, string>): FormState {
  const base = { ok: false as const, ...(values ? { values } : {}) };
  if (!(error instanceof ApiProblem)) return { ...base, formError: GENERIC_ERROR };
  if (error.code === "identity.auth.invalid_credentials") {
    return { ...base, formError: INVALID_CREDENTIALS };
  }
  if (error.status === 429) {
    return { ...base, formError: "Muitas tentativas. Aguarde um instante e tente de novo." };
  }
  if (error.status === 422) return { ...base, fieldErrors: { email: "Informe um email válido." } };
  return { ...base, formError: GENERIC_ERROR };
}

export function text(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
}

/** Senha não é aparada: espaços fazem parte dela. */
export function secret(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value : "";
}
