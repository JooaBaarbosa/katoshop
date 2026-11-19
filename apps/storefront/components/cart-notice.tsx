import { Button } from "@katoshop/ui/button";
import { Info } from "lucide-react";
import { ackNoticesAction } from "../app/(shop)/carrinho/actions";

/** Aviso de um item (preço, quantidade ou indisponível), sempre com os dados reais do cart. */
export function CartNotice({ message }: { message: string }) {
  return (
    <p className="flex items-start gap-2 text-sm text-ks-fg">
      <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-accent" />
      <span>{message}</span>
    </p>
  );
}

/**
 * Faixa no topo do /carrinho quando há aviso a confirmar: o ajuste do merge no login (flash)
 * e/ou avisos nos itens. "Entendi" limpa os dois (ackNoticesAction).
 */
export function CartNoticesBar({
  mergeAdjusted,
  itemNotices,
}: {
  mergeAdjusted: boolean;
  itemNotices: boolean;
}) {
  if (!mergeAdjusted && !itemNotices) return null;
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius)] border border-ks-border bg-ks-surface px-4 py-3"
    >
      <div className="space-y-1 text-sm">
        {mergeAdjusted && <p>Alguns itens foram ajustados ao juntar seu carrinho.</p>}
        {itemNotices && <p>Alguns itens mudaram desde que você os adicionou. Veja os avisos.</p>}
      </div>
      <form action={ackNoticesAction}>
        <Button type="submit" variant="secondary">
          Entendi
        </Button>
      </form>
    </div>
  );
}
