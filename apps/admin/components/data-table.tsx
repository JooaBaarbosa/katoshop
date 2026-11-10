"use client";

import {
  tableFeatures,
  useTable,
  type ColumnDef,
  type RowData,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@katoshop/ui/table";

/**
 * Sem recursos de ordenação ou filtro no cliente: a busca, os filtros e a paginação por cursor
 * ficam no servidor (a URL é o estado). A tabela só monta cabeçalhos e células.
 */
export const dataTableFeatures = tableFeatures({});
export type DataTableFeatures = typeof dataTableFeatures;
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- colunas com valores de tipos variados
export type DataTableColumn<TData extends RowData> = ColumnDef<DataTableFeatures, TData, any>;

export function DataTable<TData extends RowData>({
  columns,
  data,
  caption,
  empty,
  getRowId,
}: {
  columns: DataTableColumn<TData>[];
  data: TData[];
  caption: string;
  empty: string;
  getRowId: (row: TData) => string;
}) {
  const table = useTable({
    features: dataTableFeatures,
    columns,
    data,
    getRowId: (row) => getRowId(row),
  });
  const rows = table.getRowModel().rows;

  return (
    <div className="overflow-x-auto border border-ks-border bg-ks-surface">
      <Table>
        <TableCaption className="sr-only">{caption}</TableCaption>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              {group.headers.map((header) => (
                <TableHead key={header.id} scope="col">
                  {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="py-8 text-center text-ks-muted">
                {empty}
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow key={row.id}>
                {row.getAllCells().map((cell) => (
                  <TableCell key={cell.id}>
                    <table.FlexRender cell={cell} />
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
