"use client";

import { Toaster as Sonner, toast, type ToasterProps } from "sonner";

export { toast };

/** Toasts via sonner (o shadcn atual usa sonner no lugar do toast do Radix). Raio de 2px. */
export function Toaster(props: ToasterProps) {
  return (
    <Sonner
      theme="system"
      toastOptions={{
        classNames: {
          toast:
            "!rounded-[var(--radius)] !border !border-ks-border !bg-ks-surface !text-ks-fg !font-sans",
          description: "!text-ks-muted",
        },
      }}
      {...props}
    />
  );
}
