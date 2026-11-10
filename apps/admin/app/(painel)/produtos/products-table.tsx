"use client";

import { Badge } from "@katoshop/ui/badge";
import { formatBRL } from "@katoshop/ui/money";
import Link from "next/link";
import { DataTable, type DataTableColumn } from "../../../components/data-table";
import type { AdminProductRow } from "../../../lib/catalog-data";
import { STATUS_LABELS } from "../../../lib/catalog-input";
import { formatMovementDate } from "../../../lib/overview";

const COLUMNS: DataTableColumn<AdminProductRow>[] = [
  {
    id: "name",
    header: "Produto",
    accessorFn: (row) => row.name,
    cell: ({ row }) => (
      <div className="space-y-0.5">
        <Link
          href={`/produtos/${row.original.id}`}
          className="font-medium underline-offset-4 hover:underline"
        >
          {row.original.name}
        </Link>
        <p className="font-mono text-xs text-ks-muted">{row.original.slug}</p>
      </div>
    ),
  },
  {
    id: "status",
    header: "Status",
    accessorFn: (row) => row.status,
    cell: ({ row }) => (
      <Badge variant={row.original.status === "active" ? "accent" : "default"}>
        {STATUS_LABELS[row.original.status] ?? row.original.status}
      </Badge>
    ),
  },
  { id: "category", header: "Categoria", accessorFn: (row) => row.category.name },
  {
    id: "price",
    header: "Preço a partir de",
    accessorFn: (row) => row.min_price_cents,
    cell: ({ row }) =>
      row.original.min_price_cents === null ? (
        <span className="text-ks-muted">Sem variantes</span>
      ) : (
        <span className="tabular-nums">{formatBRL(row.original.min_price_cents)}</span>
      ),
  },
  {
    id: "variants",
    header: "Variantes",
    accessorFn: (row) => row.variant_count,
    cell: ({ row }) => <span className="tabular-nums">{row.original.variant_count}</span>,
  },
  {
    id: "available",
    header: "Disponível",
    accessorFn: (row) => row.total_available,
    cell: ({ row }) => <span className="tabular-nums">{row.original.total_available}</span>,
  },
  {
    id: "updated",
    header: "Atualizado em",
    accessorFn: (row) => row.updated_at,
    cell: ({ row }) => (
      <time dateTime={row.original.updated_at} className="whitespace-nowrap tabular-nums">
        {formatMovementDate(row.original.updated_at)}
      </time>
    ),
  },
];

export function ProductsTable({ items }: { items: AdminProductRow[] }) {
  return (
    <DataTable
      columns={COLUMNS}
      data={items}
      getRowId={(row) => row.id}
      caption="Produtos do catálogo, do atualizado mais recentemente para o mais antigo"
      empty="Nenhum produto encontrado com estes filtros."
    />
  );
}
