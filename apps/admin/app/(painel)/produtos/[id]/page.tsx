import { Badge } from "@katoshop/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@katoshop/ui/tabs";
import type { Metadata } from "next";
import Link from "next/link";
import { ImageManager } from "../../../../components/image-manager";
import { PageHeader } from "../../../../components/page-header";
import { ProductForm } from "../../../../components/product-form";
import { PublishChecklist } from "../../../../components/publish-checklist";
import { VariantGenerator } from "../../../../components/variant-generator";
import { VariantGrid } from "../../../../components/variant-grid";
import { getProduct, listCategories } from "../../../../lib/catalog-data";
import { STATUS_LABELS } from "../../../../lib/catalog-input";
import { requireStaff } from "../../../../lib/guard";

export const metadata: Metadata = { title: "Editar produto" };

const TABS = ["dados", "variantes", "fotos", "publicacao"] as const;

export default async function ProductPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ aba?: string }>;
}) {
  await requireStaff();
  const [{ id }, { aba }] = await Promise.all([params, searchParams]);
  const [product, categories] = await Promise.all([getProduct(id), listCategories()]);
  const tab = TABS.find((name) => name === aba) ?? "dados";

  return (
    <>
      <Link href="/produtos" className="text-sm underline-offset-4 hover:underline">
        Voltar para produtos
      </Link>
      <PageHeader
        title={product.name}
        description={`Endereço na loja: /p/${product.slug}`}
        actions={
          <Badge variant={product.status === "active" ? "accent" : "default"}>
            {STATUS_LABELS[product.status] ?? product.status}
          </Badge>
        }
      />
      <Tabs defaultValue={tab}>
        <TabsList aria-label="Seções do produto" className="flex-wrap">
          <TabsTrigger value="dados">Dados</TabsTrigger>
          <TabsTrigger value="variantes">Variantes</TabsTrigger>
          <TabsTrigger value="fotos">Fotos</TabsTrigger>
          <TabsTrigger value="publicacao">Publicação</TabsTrigger>
        </TabsList>
        <TabsContent value="dados" className="pt-4">
          <ProductForm product={product} categories={categories} />
        </TabsContent>
        <TabsContent value="variantes" className="space-y-6 pt-4">
          <VariantGrid productId={product.id} variants={product.variants} />
          <VariantGenerator productId={product.id} />
        </TabsContent>
        <TabsContent value="fotos" className="pt-4">
          <ImageManager productId={product.id} images={product.images} />
        </TabsContent>
        <TabsContent value="publicacao" className="pt-4">
          <PublishChecklist product={product} />
        </TabsContent>
      </Tabs>
    </>
  );
}
