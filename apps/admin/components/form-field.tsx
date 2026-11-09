import { Input } from "@katoshop/ui/input";
import type { ComponentProps } from "react";

type FormFieldProps = Omit<ComponentProps<"input">, "id" | "name"> & {
  name: string;
  label: string;
  error?: string | undefined;
};

/** Campo com <label> explícito; erro ligado por aria-invalid e aria-describedby. */
export function FormField({ name, label, error, ...props }: FormFieldProps) {
  const id = `field-${name}`;
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
