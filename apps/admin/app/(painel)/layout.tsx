import type { ReactNode } from "react";
import { DemoBadge } from "../../components/demo-badge";
import { Sidebar } from "../../components/sidebar";
import { requireStaff } from "../../lib/guard";

// Painel sempre por requisição: depende da sessão e de dados vivos da API (R21).
export const dynamic = "force-dynamic";

export default async function PainelLayout({ children }: { children: ReactNode }) {
  const me = await requireStaff();
  return (
    <div className="md:flex">
      <Sidebar userName={me.name} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-end border-b border-ks-border bg-ks-surface px-4 py-3 sm:px-8">
          <DemoBadge />
        </div>
        <main id="conteudo" className="space-y-8 px-4 py-8 sm:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
