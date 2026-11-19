import { ApiProblem } from "@katoshop/api-client";
import { Badge } from "@katoshop/ui/badge";
import { Button } from "@katoshop/ui/button";
import { Input } from "@katoshop/ui/input";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@katoshop/ui/table";
import { Plus, Search } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { FormNotice } from "../../../components/form-field";
import { PageHeader } from "../../../components/page-header";
import { SelectField } from "../../../components/select-field";
import { INVALID_CURSOR, listCoupons, type CouponQuery } from "../../../lib/coupon-data";
import {
  couponConditions,
  couponValueLabel,
  flashMessage,
  KIND_LABELS,
  type Coupon,
} from "../../../lib/coupons";
import { requireStaff } from "../../../lib/guard";
import { formatMovementDate } from "../../../lib/overview";
import { messageFor } from "../../../lib/problem-messages";

export const metadata: Metadata = { title: "Cupons" };

type SearchParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

const FILTER_KEYS = ["q", "status"] as const;

function queryOf(params: SearchParams): CouponQuery {
  const q = one(params.q).slice(0, 200);
  const status = one(params.status);
  const cursor = one(params.cursor);
  return {
    ...(q ? { q } : {}),
    ...(status === "ativos" ? { active: true } : status === "inativos" ? { active: false } : {}),
    ...(cursor ? { cursor } : {}),
  };
}

function listHref(params: SearchParams, cursor?: string): string {
  const search = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = one(params[key]);
    if (value) search.set(key, value);
  }
  if (cursor) search.set("cursor", cursor);
  const text = search.toString();
  return text ? `/cupons?${text}` : "/cupons";
}

function validity(coupon: Coupon): string {
  const starts = coupon.starts_at ? formatMovementDate(coupon.starts_at) : null;
  const ends = coupon.ends_at ? formatMovementDate(coupon.ends_at) : null;
  if (starts && ends) return `De ${starts} até ${ends}`;
  if (starts) return `A partir de ${starts}`;
  if (ends) return `Até ${ends}`;
  return "Sem prazo";
}

export default async function CouponsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  await requireStaff();
  const params = await searchParams;
  const query = queryOf(params);
  const flash = flashMessage(one(params.aviso) || undefined);

  let notice: string | null = null;
  let page: Awaited<ReturnType<typeof listCoupons>>;
  try {
    page = await listCoupons(query);
  } catch (error) {
    // cursor adulterado ou vencido: mostra o início da lista com um aviso
    if (!(error instanceof ApiProblem) || error.code !== INVALID_CURSOR || !query.cursor) {
      throw error;
    }
    page = await listCoupons(queryOf({ ...params, cursor: undefined }));
    notice = messageFor(INVALID_CURSOR);
  }
  const onLaterPage = Boolean(query.cursor) && notice === null;

  return (
    <>
      <PageHeader
        title="Cupons"
        description="Códigos de desconto da loja: percentual ou valor fixo, com validade, alcance e limites."
        actions={
          <Button asChild>
            <Link href="/cupons/novo">
              <Plus aria-hidden className="size-4" />
              Novo cupom
            </Link>
          </Button>
        }
      />

      <FormNotice message={flash ?? undefined} />
      {notice && (
        <p role="status" className="border border-ks-border bg-ks-surface px-3 py-2 text-sm">
          {notice}
        </p>
      )}

      <form
        method="get"
        action="/cupons"
        role="search"
        aria-label="Filtrar cupons"
        className="grid gap-4 border border-ks-border bg-ks-surface p-4 md:grid-cols-[2fr_1fr_auto] md:items-end"
      >
        <div className="space-y-2">
          <label htmlFor="busca" className="block text-sm font-medium">
            Buscar
          </label>
          <Input
            id="busca"
            name="q"
            type="search"
            maxLength={200}
            defaultValue={query.q ?? ""}
            placeholder="Código ou descrição"
          />
        </div>
        <SelectField
          name="status"
          label="Status"
          defaultValue={one(params.status) || "todos"}
          options={[
            { value: "todos", label: "Todos" },
            { value: "ativos", label: "Ativos" },
            { value: "inativos", label: "Inativos" },
          ]}
        />
        <Button type="submit" variant="secondary">
          <Search aria-hidden className="size-4" />
          Filtrar
        </Button>
      </form>

      {page.items.length === 0 ? (
        <p className="border border-ks-border bg-ks-surface p-4 text-sm text-ks-muted">
          Nenhum cupom encontrado com estes filtros.
        </p>
      ) : (
        <div className="overflow-x-auto border border-ks-border bg-ks-surface">
          <Table>
            <TableCaption className="sr-only">
              Cupons, do criado mais recentemente para o mais antigo
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Código</TableHead>
                <TableHead scope="col">Tipo</TableHead>
                <TableHead scope="col" className="text-right">
                  Valor
                </TableHead>
                <TableHead scope="col">Validade</TableHead>
                <TableHead scope="col">Condições</TableHead>
                <TableHead scope="col">Status</TableHead>
                <TableHead scope="col" className="text-right">
                  Usos
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page.items.map((coupon) => (
                <TableRow key={coupon.id}>
                  <TableCell>
                    <Link
                      href={`/cupons/${coupon.id}`}
                      className="font-mono font-medium underline-offset-4 hover:underline"
                    >
                      {coupon.code}
                    </Link>
                    {coupon.description && (
                      <p className="text-xs text-ks-muted">{coupon.description}</p>
                    )}
                  </TableCell>
                  <TableCell>{KIND_LABELS[coupon.kind]}</TableCell>
                  <TableCell className="text-right whitespace-nowrap tabular-nums">
                    {couponValueLabel(coupon)}
                  </TableCell>
                  <TableCell className="text-sm tabular-nums">{validity(coupon)}</TableCell>
                  <TableCell>
                    <ul className="space-y-0.5 text-sm">
                      {couponConditions(coupon).map((condition) => (
                        <li key={condition}>{condition}</li>
                      ))}
                    </ul>
                  </TableCell>
                  <TableCell>
                    <Badge variant={coupon.active ? "accent" : "default"}>
                      {coupon.active ? "Ativo" : "Inativo"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {coupon.max_uses_total !== null
                      ? `${coupon.uses_count} de ${coupon.max_uses_total}`
                      : coupon.uses_count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <nav aria-label="Paginação" className="flex flex-wrap items-center gap-3">
        {onLaterPage && (
          <Button asChild variant="ghost">
            <Link href={listHref(params)}>Primeira página</Link>
          </Button>
        )}
        {page.next_cursor && (
          <Button asChild variant="secondary">
            <Link href={listHref(params, page.next_cursor)}>Próxima página</Link>
          </Button>
        )}
      </nav>
    </>
  );
}
