import { Badge } from "@katoshop/ui/badge";
import type { Metadata } from "next";
import Link from "next/link";
import { CouponForm, CouponStatusToggle, DeleteCoupon } from "../../../../components/coupon-form";
import { PageHeader } from "../../../../components/page-header";
import { listCategories, listCollections } from "../../../../lib/catalog-data";
import { getCoupon } from "../../../../lib/coupon-data";
import { requireStaff } from "../../../../lib/guard";

export const metadata: Metadata = { title: "Editar cupom" };

export default async function CouponPage({ params }: { params: Promise<{ id: string }> }) {
  await requireStaff();
  const { id } = await params;
  const [coupon, categories, collections] = await Promise.all([
    getCoupon(id),
    listCategories(),
    listCollections(),
  ]);
  const uses = coupon.uses_count === 1 ? "1 uso" : `${coupon.uses_count} usos`;
  return (
    <>
      <Link href="/cupons" className="text-sm underline-offset-4 hover:underline">
        Voltar para cupons
      </Link>
      <PageHeader
        title={coupon.code}
        description={`${uses} até agora.`}
        actions={
          <div className="flex flex-wrap items-start gap-3">
            <Badge variant={coupon.active ? "accent" : "default"} className="mt-2.5">
              {coupon.active ? "Ativo" : "Inativo"}
            </Badge>
            <CouponStatusToggle coupon={coupon} />
            {coupon.uses_count === 0 && <DeleteCoupon coupon={coupon} />}
          </div>
        }
      />
      {coupon.uses_count > 0 && (
        <p className="text-sm text-ks-muted">
          Cupons já usados não podem ser excluídos. Para tirar da loja, desative.
        </p>
      )}
      <CouponForm
        coupon={coupon}
        categories={categories.map(({ slug, name }) => ({ slug, name }))}
        collections={collections.map(({ slug, name }) => ({ slug, name }))}
      />
    </>
  );
}
