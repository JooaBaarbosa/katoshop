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

const CODE_MESSAGES: Record<string, string> = {
  "identity.auth.invalid_credentials": "Email ou senha incorretos.",
};

const FIELD_CODE_MESSAGES: Record<string, [field: string, message: string]> = {
  "identity.auth.email_taken": ["email", "Já existe uma conta com este email."],
};

const PASSWORD_REASONS: Record<string, string> = {
  too_short: "Use pelo menos 10 caracteres.",
  too_common: "Essa senha é muito comum.",
  contains_email: "A senha não pode conter seu email.",
};

const FIELD_FALLBACK: Record<string, string> = {
  email: "Informe um email válido.",
  name: "Informe seu nome.",
  password: "Verifique a senha.",
};

/** `body.password` → `password`, `body.new_password` → `password`. */
function fieldOf(path: string): string {
  const name = path.split(".").at(-1) ?? path;
  return name === "new_password" ? "password" : name;
}

/** Converte um erro de chamada à API em estado de formulário com mensagens em pt-BR. */
export function problemToState(error: unknown, values?: Record<string, string>): FormState {
  const base = { ok: false as const, ...(values ? { values } : {}) };
  if (!(error instanceof ApiProblem)) return { ...base, formError: GENERIC_ERROR };

  const formMessage = CODE_MESSAGES[error.code];
  if (formMessage) return { ...base, formError: formMessage };

  const fieldMessage = FIELD_CODE_MESSAGES[error.code];
  if (fieldMessage) return { ...base, fieldErrors: { [fieldMessage[0]]: fieldMessage[1] } };

  if (error.status === 429) {
    return { ...base, formError: "Muitas tentativas. Aguarde um instante e tente de novo." };
  }

  if (error.status === 422 && error.errors) {
    const fieldErrors: Record<string, string> = {};
    for (const [path, reasons] of Object.entries(error.errors)) {
      const field = fieldOf(path);
      const known = reasons.map((reason) => PASSWORD_REASONS[reason]).filter(Boolean);
      fieldErrors[field] =
        known.length > 0 ? known.join(" ") : (FIELD_FALLBACK[field] ?? "Verifique este campo.");
    }
    return { ...base, fieldErrors };
  }

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
