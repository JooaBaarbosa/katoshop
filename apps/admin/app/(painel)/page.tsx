import { unwrap } from "@katoshop/api-client";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@katoshop/ui/table";
import type { Metadata } from "next";
import { PageHeader } from "../../components/page-header";
import { catalog } from "../../lib/api";
import { authed, requireStaff } from "../../lib/guard";
import {
  formatDelta,
  formatMovementDate,
  movementReasonLabel,
  statusCards,
  type Overview,
} from "../../lib/overview";

export const metadata: Metadata = { title: "Visão geral" };

function StatCard({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="space-y-1 border border-ks-border bg-ks-surface p-4">
      <dt className="text-xs font-semibold uppercase tracking-wide text-ks-muted">{label}</dt>
      <dd className="font-display text-4xl tabular-nums">{value}</dd>
      {hint && <dd className="text-xs text-ks-muted">{hint}</dd>}
    </div>
  );
}

export default async function OverviewPage() {
  await requireStaff();
  const overview: Overview = await authed(async (token) =>
    unwrap(await catalog(token).GET("/v1/admin/overview")),
  );
  const movements = overview.recent_movements;

  return (
    <>
      <PageHeader title="Visão geral" description="Situação atual do catálogo e do estoque." />

      <section aria-labelledby="produtos-titulo" className="space-y-3">
        <h2 id="produtos-titulo" className="text-xl">
          Produtos e estoque
        </h2>
        <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {statusCards(overview.products_by_status).map((card) => (
            <StatCard key={card.label} label={card.label} value={card.value} />
          ))}
          <StatCard
            label="Variantes sem estoque"
            value={overview.out_of_stock_variants}
            hint="Tamanho e cor com saldo zero"
          />
        </dl>
      </section>

      <section aria-labelledby="movimentos-titulo" className="space-y-3">
        <h2 id="movimentos-titulo" className="text-xl">
          Últimos movimentos de estoque
        </h2>
        {movements.length === 0 ? (
          <p className="border border-ks-border bg-ks-surface p-4 text-sm text-ks-muted">
            Nenhum movimento de estoque registrado ainda.
          </p>
        ) : (
          <div className="border border-ks-border bg-ks-surface">
            <Table>
              <TableCaption className="sr-only">
                Movimentos mais recentes, do mais novo para o mais antigo
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead>SKU</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead className="text-right">Quantidade</TableHead>
                  <TableHead>Observação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {movements.map((movement) => (
                  <TableRow key={movement.id}>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      <time dateTime={movement.created_at}>
                        {formatMovementDate(movement.created_at)}
                      </time>
                    </TableCell>
                    <TableCell>{movement.product_name}</TableCell>
                    <TableCell className="font-mono text-xs">{movement.sku}</TableCell>
                    <TableCell>{movementReasonLabel(movement.reason)}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatDelta(movement.delta)}
                    </TableCell>
                    <TableCell className="text-ks-muted">{movement.note ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </>
  );
}
