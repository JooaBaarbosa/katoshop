import type { Metadata } from "next";
import Link from "next/link";
import { safeNext } from "../../../lib/safe-next";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Entrar" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { next } = await searchParams;
  const destination = safeNext(typeof next === "string" ? next : null);
  return (
    <section className="mx-auto max-w-sm space-y-8">
      <div className="space-y-2">
        <h1 className="text-4xl">Entrar</h1>
        <p className="text-sm text-ks-muted">Acesse sua conta para ver e editar seus dados.</p>
      </div>
      <LoginForm next={destination} />
      <p className="text-sm text-ks-muted">
        Ainda não tem conta?{" "}
        <Link href="/criar-conta" className="font-semibold text-ks-fg underline underline-offset-4">
          Criar conta
        </Link>
      </p>
    </section>
  );
}
