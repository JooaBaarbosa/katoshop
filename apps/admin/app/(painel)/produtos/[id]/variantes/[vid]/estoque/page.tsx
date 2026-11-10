import { ApiProblem } from "@katoshop/api-client";
import { Button } from "@katoshop/ui/button";
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
import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeader } from "../../../../../../../components/page-header";
import { StockAdjustForm } from "../../../../../../../components/stock-adjust-form";
import { getProduct, listMovements } from "../../../../../../../lib/catalog-data";
import { colorName } from "../../../../../../../lib/catalog-input";
import { requireStaff } from "../../../../../../../lib/guard";
import {
  formatDelta,
  formatMovementDate,
  movementReasonLabel,
} from "../../../../../../../lib/overview";
import { problemMessage } from "../../../../../../../lib/problem-messages";

export const metadata: Metadata = { title: "Estoque da variante" };

export default async function StockPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; vid: string }>;
  searchParams: Promise<{ cursor?: string }>;
}) {
  const me = await requireStaff();
  const [{ id, vid }, { cursor }] = await Promise.all([params, searchParams]);
  const product = await getProduct(id);
  const variant = product.variants.find((item) => item.id === vid);
  if (!variant) notFound();

  let page: Awaited<ReturnType<typeof listMovements>> | null = null;
  let listError: string | null = null;
  try {
    page = await listMovements(vid, cursor);
  } catch (error) {
    if (!(error instanceof ApiProblem) || error.status !== 422) throw error;
    listError = problemMessage(error);
  }

  const base = `/produtos/${id}/variantes/${vid}/estoque`;
  const author = (actorId: string | null) =>
    actorId === null ? "Sistema" : actorId === me.id ? `${me.name} (você)` : `Equipe ${actorId.slice(-6)}`;

  return (
    <>
      <Link
        href={`/produtos/${id}?aba=variantes`}
        className="text-sm underline-offset-4 hover:underline"
      >
        Voltar para as variantes de {product.name}
      </Link>
      <PageHeader
        title={`Estoque ${colorName(variant.color_code)} ${variant.size_code}`}
        description={`${product.name} · SKU ${variant.sku}`}
      />

      <dl className="grid max-w-xl grid-cols-3 gap-3">
        {(
          [
            ["Em estoque", variant.stock_on_hand],
            ["Reservado", variant.stock_reserved],
            ["Disponível", variant.available],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="space-y-1 border border-ks-border bg-ks-surface p-4">
            <dt className="text-xs font-semibold uppercase tracking-wide text-ks-muted">{label}</dt>
            <dd className="font-display text-3xl tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      <StockAdjustForm productId={id} variantId={vid} />

      <section aria-labelledby="movimentos" className="space-y-3">
        <h2 id="movimentos" className="text-xl">
          Livro razão
        </h2>
        {listError || !page ? (
          <p role="alert" className="border border-ks-border bg-ks-surface p-4 text-sm">
            {listError}{" "}
            <Link href={base} className="font-medium underline underline-offset-4">
              Voltar ao início
            </Link>
          </p>
        ) : page.items.length === 0 ? (
          <p className="border border-ks-border bg-ks-surface p-4 text-sm text-ks-muted">
            Nenhum movimento registrado para esta variante.
          </p>
        ) : (
          <div className="overflow-x-auto border border-ks-border bg-ks-surface">
            <Table>
              <TableCaption className="sr-only">
                Movimentos de estoque, do mais novo para o mais antigo
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Data</TableHead>
                  <TableHead scope="col" className="text-right">
                    Quantidade
                  </TableHead>
                  <TableHead scope="col">Motivo</TableHead>
                  <TableHead scope="col">Nota</TableHead>
                  <TableHead scope="col">Autor</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.items.map((movement) => (
                  <TableRow key={movement.id}>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      <time dateTime={movement.created_at}>
                        {formatMovementDate(movement.created_at)}
                      </time>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {formatDelta(movement.delta)}
                    </TableCell>
                    <TableCell>{movementReasonLabel(movement.reason)}</TableCell>
                    <TableCell className="text-ks-muted">{movement.note ?? ""}</TableCell>
                    <TableCell>{author(movement.actor_id)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <nav aria-label="Paginação" className="flex gap-3">
          {cursor && (
            <Button asChild variant="ghost">
              <Link href={base}>Mais recentes</Link>
            </Button>
          )}
          {page?.next_cursor && (
            <Button asChild variant="secondary">
              <Link href={`${base}?cursor=${encodeURIComponent(page.next_cursor)}`}>
                Movimentos anteriores
              </Link>
            </Button>
          )}
        </nav>
      </section>
    </>
  );
}
