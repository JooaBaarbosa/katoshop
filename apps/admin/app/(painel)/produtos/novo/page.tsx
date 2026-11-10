import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "../../../../components/page-header";
import { ProductForm } from "../../../../components/product-form";
import { listCategories } from "../../../../lib/catalog-data";
import { requireStaff } from "../../../../lib/guard";

export const metadata: Metadata = { title: "Novo produto" };

export default async function NewProductPage() {
  await requireStaff();
  const categories = await listCategories();
  return (
    <>
      <Link href="/produtos" className="text-sm underline-offset-4 hover:underline">
        Voltar para produtos
      </Link>
      <PageHeader
        title="Novo produto"
        description="O produto nasce como rascunho. Depois de criar, gere as variantes, envie as fotos e publique."
      />
      {categories.length === 0 ? (
        <p className="border border-ks-border bg-ks-surface p-4 text-sm">
          Crie uma categoria antes do primeiro produto.{" "}
          <Link href="/categorias" className="font-medium underline underline-offset-4">
            Ir para categorias
          </Link>
        </p>
      ) : (
        <ProductForm categories={categories} />
      )}
    </>
  );
}
