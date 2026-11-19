import type { Metadata } from "next";
import Link from "next/link";
import { CouponForm } from "../../../../components/coupon-form";
import { PageHeader } from "../../../../components/page-header";
import { listCategories, listCollections } from "../../../../lib/catalog-data";
import { requireStaff } from "../../../../lib/guard";

export const metadata: Metadata = { title: "Novo cupom" };

export default async function NewCouponPage() {
  await requireStaff();
  const [categories, collections] = await Promise.all([listCategories(), listCollections()]);
  return (
    <>
      <Link href="/cupons" className="text-sm underline-offset-4 hover:underline">
        Voltar para cupons
      </Link>
      <PageHeader
        title="Novo cupom"
        description="O cliente digita o código no carrinho. O código não muda depois de criado."
      />
      <CouponForm
        categories={categories.map(({ slug, name }) => ({ slug, name }))}
        collections={collections.map(({ slug, name }) => ({ slug, name }))}
      />
    </>
  );
}
