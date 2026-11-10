"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@katoshop/ui/select";

export type SelectOption = { value: string; label: string };

/**
 * Select do kit com <label> e erro ligados. Com `name` dentro de um <form>, o Radix envia o
 * valor num select nativo oculto. Radix não aceita valor vazio: use um valor como "none".
 */
export function SelectField({
  name,
  label,
  options,
  defaultValue,
  placeholder,
  error,
  required,
  idSuffix = "",
}: {
  name: string;
  label: string;
  options: SelectOption[];
  defaultValue?: string | undefined;
  placeholder?: string;
  error?: string | undefined;
  required?: boolean;
  /** Distingue ids quando o mesmo campo aparece em vários formulários da página. */
  idSuffix?: string;
}) {
  const id = `field-${name}${idSuffix}`;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="space-y-2">
      <label id={`${id}-label`} htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <Select name={name} defaultValue={defaultValue} required={required}>
        <SelectTrigger
          id={id}
          aria-labelledby={`${id}-label`}
          aria-invalid={error ? true : undefined}
          aria-describedby={errorId}
        >
          <SelectValue placeholder={placeholder ?? "Escolha"} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && (
        <p id={errorId} className="text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
