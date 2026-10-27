import { Input } from "@katoshop/ui/input";
import type { ComponentProps } from "react";

type FormFieldProps = Omit<ComponentProps<"input">, "id" | "name"> & {
  name: string;
  label: string;
  error?: string | undefined;
  hint?: string;
};

/** Campo com <label> explícito; erro ligado por aria-invalid e aria-describedby. */
export function FormField({ name, label, error, hint, ...props }: FormFieldProps) {
  const id = `field-${name}`;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <Input
        id={id}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...props}
      />
      {hint && (
        <p id={hintId} className="text-xs text-ks-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-sm text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}

export function FormError({ message }: { message?: string | undefined }) {
  if (!message) return null;
  return (
    <p role="alert" className="border border-red-500/60 px-3 py-2 text-sm text-red-300">
      {message}
    </p>
  );
}
