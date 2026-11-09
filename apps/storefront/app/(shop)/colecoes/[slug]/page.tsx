import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ProductListing } from "../../../../components/product-listing";
import { parseFilters, type RawSearchParams } from "../../../../lib/filters";
import { collectionBySlug } from "../../../../lib/storefront";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<RawSearchParams>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const result = await collectionBySlug((await params).slug);
  if (!result.ok) return { title: "Coleção" };
  const collection = result.data;
  return {
    title: collection.name,
    description:
      collection.description ?? `Coleção ${collection.name} da KatoShop, loja demonstrativa.`,
    alternates: { canonical: `/colecoes/${collection.slug}` },
  };
}

export default async function CollectionPage({ params, searchParams }: Props) {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  const result = await collectionBySlug(slug);
  if (!result.ok && result.reason === "not_found") notFound();
  if (!result.ok) throw new Error("Catálogo indisponível ao carregar a coleção");
  const collection = result.data;

  return (
    <ProductListing
      scope={{ collection: collection.slug }}
      filters={parseFilters(sp)}
      action={`/colecoes/${collection.slug}`}
      header={
        <>
          <p className="text-xs font-semibold uppercase tracking-wide text-ks-muted">Coleção</p>
          <h1 className="text-5xl">{collection.name}</h1>
          {collection.description && (
            <p className="max-w-prose text-sm text-ks-muted">{collection.description}</p>
          )}
        </>
      }
    />
  );
}
