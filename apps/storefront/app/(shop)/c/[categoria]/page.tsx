import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ProductListing } from "../../../../components/product-listing";
import { parseFilters, type RawSearchParams } from "../../../../lib/filters";
import { cache } from "react";
import { categoryBySlug, type PublicCategory } from "../../../../lib/storefront";

type Props = {
  params: Promise<{ categoria: string }>;
  searchParams: Promise<RawSearchParams>;
};

/** 404 só para slug inexistente; catálogo fora do ar lança para a página de erro. */
const findCategory = cache(async (slug: string): Promise<PublicCategory> => {
  const result = await categoryBySlug(slug);
  if (result.ok) return result.data;
  if (result.reason === "not_found") notFound();
  throw new Error("Catálogo indisponível ao carregar a categoria");
});

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const category = await findCategory((await params).categoria);
  return {
    title: category.name,
    description: `${category.name} da KatoShop, loja demonstrativa de streetwear em tecido pesado.`,
    alternates: { canonical: `/c/${category.slug}` },
  };
}

export default async function CategoryPage({ params, searchParams }: Props) {
  const [{ categoria }, sp] = await Promise.all([params, searchParams]);
  const category = await findCategory(categoria);

  return (
    <ProductListing
      scope={{ category: category.slug }}
      filters={parseFilters(sp)}
      action={`/c/${category.slug}`}
      header={<h1 className="text-5xl">{category.name}</h1>}
    />
  );
}
