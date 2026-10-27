import type { Metadata } from "next";
import Link from "next/link";
import { RegisterForm } from "./register-form";

export const metadata: Metadata = { title: "Criar conta" };

export default function RegisterPage() {
  return (
    <section className="mx-auto max-w-sm space-y-8">
      <div className="space-y-2">
        <h1 className="text-4xl">Criar conta</h1>
        <p className="text-sm text-ks-muted">
          Conta de demonstração: use um email de teste. Nenhuma compra é real.
        </p>
      </div>
      <RegisterForm />
      <p className="text-sm text-ks-muted">
        Já tem conta?{" "}
        <Link href="/entrar" className="font-semibold text-ks-fg underline underline-offset-4">
          Entrar
        </Link>
      </p>
    </section>
  );
}
