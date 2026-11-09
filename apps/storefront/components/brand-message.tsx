import { Logo } from "@katoshop/ui/logo";
import type { ReactNode } from "react";

/** Miolo compartilhado das páginas de erro e 404 (marca, título, texto e ações). */
export function BrandMessage({
  title,
  children,
  actions,
}: {
  title: string;
  children?: ReactNode;
  actions: ReactNode;
}) {
  return (
    <div className="mx-auto flex min-h-[60dvh] w-full max-w-xl flex-col items-start justify-center gap-6 px-4 py-16">
      <Logo tone="dark" className="h-7" />
      <h1 className="text-5xl">{title}</h1>
      {children && <div className="space-y-2 text-sm text-ks-muted">{children}</div>}
      <div className="flex flex-wrap gap-3">{actions}</div>
    </div>
  );
}
