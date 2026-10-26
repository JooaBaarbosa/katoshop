import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("rounded-[var(--radius)] bg-ks-fg/10 motion-safe:animate-pulse", className)}
      {...props}
    />
  );
}
