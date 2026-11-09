import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ProductListing } from "../../../../components/product-listing";
import { parseFilters, type RawSearchParams } from "../../../../lib/filters";
import { allCategories } from "../../../../lib/storefront";

export const revalidate = 60;

type Props = {
  params: Promise<{ categoria: string }>;
  searchParams: Promise<RawSearchParams>;
};

async function findCategory(slug: string) {
  return (await allCategories()).find((category) => category.slug === slug);
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const category = await findCategory((await params).categoria);
  if (!category) return { title: "Categoria não encontrada" };
  return {
    title: category.name,
    description: `${category.name} da KatoShop, loja demonstrativa de streetwear em tecido pesado.`,
    alternates: { canonical: `/c/${category.slug}` },
  };
}

export default async function CategoryPage({ params, searchParams }: Props) {
  const [{ categoria }, sp] = await Promise.all([params, searchParams]);
  const category = await findCategory(categoria);
  if (!category) notFound();

  return (
    <ProductListing
      scope={{ category: category.slug }}
      filters={parseFilters(sp)}
      action={`/c/${category.slug}`}
      header={<h1 className="text-5xl">{category.name}</h1>}
    />
  );
}
