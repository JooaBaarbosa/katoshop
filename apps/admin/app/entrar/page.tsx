import { Logo } from "@katoshop/ui/logo";
import type { Metadata } from "next";
import { DemoBadge } from "../../components/demo-badge";
import { safeNext } from "../../lib/safe-next";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Entrar" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { next, erro } = await searchParams;
  const destination = safeNext(typeof next === "string" ? next : null, "/");
  return (
    <main id="conteudo" className="flex min-h-dvh items-center justify-center px-4 py-16">
      <section className="w-full max-w-sm space-y-8 border border-ks-border bg-ks-surface p-6 sm:p-8">
        <div className="flex items-center justify-between gap-4">
          <Logo tone="light" />
          <DemoBadge />
        </div>
        <div className="space-y-2">
          <h1 className="text-3xl">Entrar no painel</h1>
          <p className="text-sm text-ks-muted">
            Área da equipe para cadastrar produtos e acompanhar o estoque.
          </p>
        </div>
        {erro === "acesso" && (
          <p role="status" className="border border-ks-border bg-ks-bg px-3 py-2 text-sm">
            Esta conta não tem acesso ao painel. Entre com uma conta da equipe.
          </p>
        )}
        <LoginForm next={destination} />
      </section>
    </main>
  );
}
