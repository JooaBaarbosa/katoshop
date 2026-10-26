import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full rounded-[var(--radius)] border border-border bg-surface px-3 text-sm text-fg transition-colors duration-[var(--duration-fast)] placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-red-500",
        className,
      )}
      {...props}
    />
  );
}
