import { formatBRL, installments, pixPrice } from "@katoshop/ui/money";
import type { Policies } from "../lib/storefront";

/** Preço em mono limão, parcelamento e Pix conforme a política da loja demo. */
export function PriceBlock({
  cents,
  from = false,
  policies,
}: {
  cents: number;
  /** Mostra "A partir de" quando o preço depende do tamanho ainda não escolhido. */
  from?: boolean;
  policies: Policies | null;
}) {
  // Sem o total parcelado: a parcela arredonda para cima e a soma pode passar do preço.
  const plan =
    policies && policies.max_installments > 1
      ? installments(cents, policies.max_installments)
      : null;
  const pixPercent = policies?.pix_discount_percent ?? 0;
  return (
    <div className="space-y-1">
      {from && <p className="text-xs uppercase tracking-wide text-ks-muted">A partir de</p>}
      <p className="font-mono text-3xl text-accent">{formatBRL(cents)}</p>
      {plan && (
        <p className="text-sm text-ks-muted">
          ou {plan.count}x de <span className="font-mono">{formatBRL(plan.eachCents)}</span> sem
          juros
        </p>
      )}
      {pixPercent > 0 && (
        <p className="text-sm text-ks-muted">
          {pixPercent}% off no Pix:{" "}
          <span className="font-mono text-ks-fg">{formatBRL(pixPrice(cents, pixPercent))}</span>
        </p>
      )}
    </div>
  );
}
