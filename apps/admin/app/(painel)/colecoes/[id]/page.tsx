import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "../../../../components/page-header";
import { getCollection, listAllProducts } from "../../../../lib/catalog-data";
import { requireStaff } from "../../../../lib/guard";
import { CollectionForm, DeleteCollection } from "../collection-form";
import { CollectionProducts } from "../collection-products";

export const metadata: Metadata = { title: "Editar coleção" };

export default async function CollectionPage({ params }: { params: Promise<{ id: string }> }) {
  await requireStaff();
  const { id } = await params;
  const [collection, products] = await Promise.all([getCollection(id), listAllProducts()]);
  return (
    <>
      <Link href="/colecoes" className="text-sm underline-offset-4 hover:underline">
        Voltar para coleções
      </Link>
      <PageHeader
        title={collection.name}
        description={`Endereço na loja: /colecoes/${collection.slug}`}
        actions={<DeleteCollection collection={collection} />}
      />
      <CollectionForm collection={collection} />
      <CollectionProducts
        collectionId={collection.id}
        productIds={collection.product_ids}
        products={products}
      />
    </>
  );
}
