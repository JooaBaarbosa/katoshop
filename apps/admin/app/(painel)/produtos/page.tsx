import { ApiProblem } from "@katoshop/api-client";
import { Button } from "@katoshop/ui/button";
import { Input } from "@katoshop/ui/input";
import { Plus, Search } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "../../../components/page-header";
import { SelectField } from "../../../components/select-field";
import {
  listCategories,
  listProducts,
  type ProductQuery,
  type ProductStatus,
} from "../../../lib/catalog-data";
import { STATUS_LABELS } from "../../../lib/catalog-input";
import { requireStaff } from "../../../lib/guard";
import { problemMessage } from "../../../lib/problem-messages";
import { ProductsTable } from "./products-table";

export const metadata: Metadata = { title: "Produtos" };

type SearchParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

const STATUSES = new Set<string>(["draft", "active", "archived"]);

function queryOf(params: SearchParams): ProductQuery {
  const q = one(params.q).slice(0, 200);
  const status = one(params.status);
  const category = one(params.categoria);
  const cursor = one(params.cursor);
  return {
    ...(q ? { q } : {}),
    ...(STATUSES.has(status) ? { status: status as ProductStatus } : {}),
    ...(category && category !== "all" ? { category } : {}),
    ...(cursor ? { cursor } : {}),
  };
}

function nextHref(params: SearchParams, cursor: string): string {
  const search = new URLSearchParams();
  for (const key of ["q", "status", "categoria"]) {
    const value = one(params[key]);
    if (value) search.set(key, value);
  }
  search.set("cursor", cursor);
  return `/produtos?${search.toString()}`;
}

function firstPageHref(params: SearchParams): string {
  const search = new URLSearchParams();
  for (const key of ["q", "status", "categoria"]) {
    const value = one(params[key]);
    if (value) search.set(key, value);
  }
  const text = search.toString();
  return text ? `/produtos?${text}` : "/produtos";
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  await requireStaff();
  const params = await searchParams;
  const query = queryOf(params);
  const categories = await listCategories();

  let page: Awaited<ReturnType<typeof listProducts>> | null = null;
  let listError: string | null = null;
  try {
    page = await listProducts(query);
  } catch (error) {
    // cursor adulterado ou vencido (422) fica na página; o resto vai para a página de erro
    if (!(error instanceof ApiProblem) || error.status !== 422) throw error;
    listError = problemMessage(error);
  }

  return (
    <>
      <PageHeader
        title="Produtos"
        description="Busque, filtre e edite os produtos do catálogo."
        actions={
          <Button asChild>
            <Link href="/produtos/novo">
              <Plus aria-hidden className="size-4" />
              Novo produto
            </Link>
          </Button>
        }
      />

      <form
        method="get"
        action="/produtos"
        role="search"
        aria-label="Filtrar produtos"
        className="grid gap-4 border border-ks-border bg-ks-surface p-4 md:grid-cols-[2fr_1fr_1fr_auto] md:items-end"
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
            placeholder="Nome ou descrição"
          />
        </div>
        <SelectField
          name="status"
          label="Status"
          defaultValue={query.status ?? "all"}
          options={[
            { value: "all", label: "Todos" },
            ...Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <SelectField
          name="categoria"
          label="Categoria"
          defaultValue={query.category ?? "all"}
          options={[
            { value: "all", label: "Todas" },
            ...categories.map((category) => ({ value: category.slug, label: category.name })),
          ]}
        />
        <Button type="submit" variant="secondary">
          <Search aria-hidden className="size-4" />
          Filtrar
        </Button>
      </form>

      {listError || !page ? (
        <div role="alert" className="space-y-3 border border-ks-border bg-ks-surface p-4 text-sm">
          <p>{listError}</p>
          <Link href={firstPageHref(params)} className="font-medium underline underline-offset-4">
            Voltar ao início da lista
          </Link>
        </div>
      ) : (
        <>
          <ProductsTable items={page.items} />
          <nav aria-label="Paginação" className="flex flex-wrap items-center gap-3">
            {query.cursor && (
              <Button asChild variant="ghost">
                <Link href={firstPageHref(params)}>Primeira página</Link>
              </Button>
            )}
            {page.next_cursor && (
              <Button asChild variant="secondary">
                <Link href={nextHref(params, page.next_cursor)}>Próxima página</Link>
              </Button>
            )}
          </nav>
        </>
      )}
    </>
  );
}
