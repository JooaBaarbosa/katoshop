import type { Metadata } from "next";
import { PageHeader } from "../../../components/page-header";
import { listCategories } from "../../../lib/catalog-data";
import { requireStaff } from "../../../lib/guard";
import { CategoryManager } from "./category-manager";

export const metadata: Metadata = { title: "Categorias" };

export default async function CategoriesPage() {
  await requireStaff();
  const categories = await listCategories();
  return (
    <>
      <PageHeader
        title="Categorias"
        description="Organize o menu da loja. Subcategorias ficam dentro de uma categoria pai."
      />
      <CategoryManager categories={categories} />
    </>
  );
}
