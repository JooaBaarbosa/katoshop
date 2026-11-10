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
import { PageHeader } from "../../../components/page-header";
import { listCollections } from "../../../lib/catalog-data";
import { requireStaff } from "../../../lib/guard";
import { CollectionForm } from "./collection-form";

export const metadata: Metadata = { title: "Coleções" };

export default async function CollectionsPage() {
  await requireStaff();
  const collections = await listCollections();
  return (
    <>
      <PageHeader
        title="Coleções"
        description="Vitrines temáticas da loja. As coleções em destaque aparecem na página inicial."
      />

      <section aria-labelledby="lista-colecoes" className="space-y-3">
        <h2 id="lista-colecoes" className="text-xl">
          Coleções
        </h2>
        {collections.length === 0 ? (
          <p className="border border-ks-border bg-ks-surface p-4 text-sm text-ks-muted">
            Nenhuma coleção cadastrada.
          </p>
        ) : (
          <div className="overflow-x-auto border border-ks-border bg-ks-surface">
            <Table>
              <TableCaption className="sr-only">Coleções do catálogo</TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Nome</TableHead>
                  <TableHead scope="col">Endereço</TableHead>
                  <TableHead scope="col">Destaque</TableHead>
                  <TableHead scope="col" className="text-right">
                    Produtos
                  </TableHead>
                  <TableHead scope="col" className="text-right">
                    Posição
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {collections.map((collection) => (
                  <TableRow key={collection.id}>
                    <TableCell>
                      <Link
                        href={`/colecoes/${collection.id}`}
                        className="font-medium underline-offset-4 hover:underline"
                      >
                        {collection.name}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{collection.slug}</TableCell>
                    <TableCell>{collection.featured ? "Sim" : "Não"}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {collection.product_ids.length}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{collection.position}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <section aria-labelledby="nova-colecao" className="space-y-3 border border-ks-border bg-ks-surface p-4">
        <h2 id="nova-colecao" className="text-xl">
          Nova coleção
        </h2>
        <CollectionForm />
      </section>
    </>
  );
}
