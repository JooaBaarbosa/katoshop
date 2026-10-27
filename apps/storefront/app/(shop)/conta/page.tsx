import { ApiProblem, unwrap } from "@katoshop/api-client";
import { Button } from "@katoshop/ui/button";
import { LogOut } from "lucide-react";
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { identity } from "../../../lib/api";
import { session } from "../../../lib/session";
import { logoutAction } from "./actions";
import { ProfileForm } from "./profile-form";

export const metadata: Metadata = { title: "Minha conta" };

async function loadMe() {
  try {
    // Server Component: só leitura; a renovação acontece no proxy.ts (R18)
    return await session.withAuth(async (token) => unwrap(await identity(token).GET("/v1/me")));
  } catch (error) {
    if (error instanceof ApiProblem && error.status === 401) redirect("/entrar?next=/conta");
    throw error;
  }
}

export default async function AccountPage() {
  const me = await loadMe();
  return (
    <section className="mx-auto max-w-lg space-y-10">
      <div className="space-y-2">
        <h1 className="text-4xl">Olá, {me.name}</h1>
        <p className="text-sm text-ks-muted">{me.email}</p>
      </div>

      <div className="space-y-4 border border-ks-border p-6">
        <h2 className="text-xl">Seus dados</h2>
        <ProfileForm name={me.name} />
      </div>

      <form action={logoutAction}>
        <Button type="submit" variant="ghost">
          <LogOut aria-hidden className="size-4" />
          Sair
        </Button>
      </form>
    </section>
  );
}
