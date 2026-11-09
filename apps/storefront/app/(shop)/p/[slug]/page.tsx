import { Button } from "@katoshop/ui/button";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { PdpGallery } from "../../../../components/pdp-gallery";
import { PriceBlock } from "../../../../components/price-block";
import { VariantPicker } from "../../../../components/variant-picker";
import { siteUrl } from "../../../../lib/env";
import type { RawSearchParams } from "../../../../lib/filters";
import { findVariant, imagesForColor, type ProductDetail, sizeStates } from "../../../../lib/pdp";
import { productDetail, storePolicies } from "../../../../lib/storefront";

type Props = { params: Promise<{ slug: string }>; searchParams: Promise<RawSearchParams> };

/** Uma busca por requisição, compartilhada entre metadata e página. */
const loadProduct = cache(async (slug: string): Promise<ProductDetail> => {
  const result = await productDetail(slug);
  if (result.ok) return result.data;
  if (result.reason === "not_found") notFound();
  throw new Error("Catálogo indisponível ao carregar o produto");
});

function single(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function summary(detail: ProductDetail): string {
  const text = detail.description?.trim();
  if (!text) return `${detail.name} na KatoShop, loja demonstrativa de streetwear.`;
  return text.length > 160 ? `${text.slice(0, 157).trimEnd()}...` : text;
}

/** Atributos simples (texto ou número) para a lista de detalhes. */
function attributeRows(attributes: Record<string, unknown>): [string, string][] {
  return Object.entries(attributes)
    .filter((entry): entry is [string, string | number] =>
      ["string", "number"].includes(typeof entry[1]),
    )
    .map(([key, value]) => {
      const label = key.replaceAll("_", " ");
      return [label.charAt(0).toUpperCase() + label.slice(1), String(value)];
    });
}

function productJsonLd(detail: ProductDetail, url: string) {
  const available = detail.variants.some((variant) => variant.available);
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: detail.name,
    ...(detail.description ? { description: detail.description } : {}),
    image: detail.images.map((image) => image.url),
    category: detail.category.name,
    brand: { "@type": "Brand", name: "KatoShop" },
    offers: {
      "@type": "Offer",
      url,
      price: (detail.min_price_cents / 100).toFixed(2),
      priceCurrency: "BRL",
      availability: available ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
    },
  };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const detail = await loadProduct((await params).slug);
  const image = detail.images[0];
  const description = summary(detail);
  return {
    title: detail.name,
    description,
    alternates: { canonical: `/p/${detail.slug}` },
    openGraph: {
      title: detail.name,
      description,
      url: `/p/${detail.slug}`,
      ...(image
        ? { images: [{ url: image.url, width: image.width, height: image.height, alt: image.alt }] }
        : {}),
    },
  };
}

export default async function ProductPage({ params, searchParams }: Props) {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  const [detail, policies] = await Promise.all([loadProduct(slug), storePolicies()]);

  const requestedColor = single(sp.cor);
  const color =
    detail.colors.find((c) => c.code === requestedColor)?.code ??
    detail.colors.find((c) => detail.variants.some((v) => v.color_code === c.code && v.available))
      ?.code ??
    detail.colors[0]?.code ??
    "";
  const requestedSize = single(sp.tamanho);
  const size = sizeStates(detail, color).some(
    (s) => s.code === requestedSize && s.state === "available",
  )
    ? requestedSize
    : undefined;

  const variant = findVariant(detail, color, size);
  const colorPrices = detail.variants
    .filter((v) => v.color_code === color)
    .map((v) => v.price_cents);
  const lowest = colorPrices.length > 0 ? Math.min(...colorPrices) : detail.min_price_cents;
  const price = variant?.price_cents ?? lowest;
  const priceVaries = !variant && new Set(colorPrices).size > 1;

  const forColor = imagesForColor(detail.images, color);
  const images = forColor.length > 0 ? forColor : detail.images;
  const attributes = attributeRows(detail.attributes);
  const jsonLd = JSON.stringify(productJsonLd(detail, `${siteUrl()}/p/${detail.slug}`)).replace(
    /</g,
    "\\u003c",
  );

  return (
    <article className="space-y-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd }} />
      <nav aria-label="Trilha" className="text-xs uppercase tracking-wide text-ks-muted">
        <ol className="flex flex-wrap gap-2">
          <li>
            <Link href="/" className="hover:text-ks-fg">
              Início
            </Link>
          </li>
          <li aria-hidden>/</li>
          <li>
            <Link href={`/c/${detail.category.slug}`} className="hover:text-ks-fg">
              {detail.category.name}
            </Link>
          </li>
          <li aria-hidden>/</li>
          <li aria-current="page" className="text-ks-fg">
            {detail.name}
          </li>
        </ol>
      </nav>

      <div className="grid gap-10 lg:grid-cols-[7fr_5fr]">
        <PdpGallery key={color} images={images} productName={detail.name} />

        <div className="space-y-8 lg:sticky lg:top-6 lg:self-start">
          <div className="space-y-4">
            <h1 className="text-4xl sm:text-5xl">{detail.name}</h1>
            <PriceBlock cents={price} from={priceVaries} policies={policies} />
          </div>

          {detail.colors.length > 0 && <VariantPicker detail={detail} color={color} size={size} />}

          <div className="space-y-2">
            <Button type="button" size="lg" className="w-full" disabled>
              Adicionar ao carrinho
            </Button>
            <p className="text-sm text-ks-muted">Carrinho chega na próxima versão</p>
          </div>

          {(detail.description || attributes.length > 0) && (
            <section aria-labelledby="pdp-detalhes" className="space-y-4 border-t border-ks-border pt-6">
              <h2 id="pdp-detalhes" className="text-2xl">
                Detalhes
              </h2>
              {detail.description && (
                <p className="whitespace-pre-line text-sm leading-relaxed">{detail.description}</p>
              )}
              {attributes.length > 0 && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
                  {attributes.map(([label, value]) => (
                    <div key={label} className="contents">
                      <dt className="text-ks-muted">{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>
          )}
        </div>
      </div>
    </article>
  );
}
