import { Input } from "@katoshop/ui/input";
import type { ComponentProps } from "react";

type FormFieldProps = Omit<ComponentProps<"input">, "id" | "name"> & {
  name: string;
  label: string;
  error?: string | undefined;
  /** Distingue ids quando o mesmo campo aparece em vários formulários da página. */
  idSuffix?: string;
};

/** Campo com <label> explícito; erro ligado por aria-invalid e aria-describedby. */
export function FormField({ name, label, error, idSuffix = "", ...props }: FormFieldProps) {
  const id = `field-${name}${idSuffix}`;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <Input
        id={id}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        {...props}
      />
      {error && (
        <p id={errorId} className="text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}

export function FormError({ message }: { message?: string | undefined }) {
  if (!message) return null;
  return (
    <p role="alert" className="border border-red-700 bg-red-50 px-3 py-2 text-sm text-red-800">
      {message}
    </p>
  );
}

type TextareaFieldProps = Omit<ComponentProps<"textarea">, "id" | "name"> & {
  name: string;
  label: string;
  hint?: string;
  error?: string | undefined;
};

export function TextareaField({ name, label, hint, error, ...props }: TextareaFieldProps) {
  const id = `field-${name}`;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <textarea
        id={id}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className="min-h-24 w-full rounded-[var(--radius)] border border-ks-border bg-ks-surface px-3 py-2 text-sm text-ks-fg transition-colors duration-[var(--duration-fast)] placeholder:text-ks-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ks-focus aria-invalid:border-red-500"
        {...props}
      />
      {hint && (
        <p id={hintId} className="text-xs text-ks-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}

/** Confirmação de sucesso anunciada por leitores de tela. */
export function FormNotice({ message }: { message?: string | undefined }) {
  if (!message) return null;
  return (
    <p role="status" className="border border-green-700 bg-green-50 px-3 py-2 text-sm text-green-800">
      {message}
    </p>
  );
}
