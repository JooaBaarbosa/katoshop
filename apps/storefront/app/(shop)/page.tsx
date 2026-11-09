import { Button } from "@katoshop/ui/button";
import { ArrowRight, CreditCard, QrCode, RefreshCcw, Truck } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { ProductGrid } from "../../components/product-grid";
import { safeNext } from "../../lib/safe-next";
import {
  collectionBySlug,
  listProducts,
  mediaUrl,
  type Policies,
  storeSettings,
} from "../../lib/storefront";

// Ruling R21: renderização por requisição (o build não alcança o catálogo e congelaria o
// fallback). A revalidação de 60 s fica na camada de dados: cada fetch usa next.revalidate = 60.
export const dynamic = "force-dynamic";

const NEW_ARRIVALS = 8;
const PER_COLLECTION = 4;

/** Texto da spec (seção 6) para quando a loja ainda não tem configurações salvas. */
const FALLBACK_HERO = {
  title: "Streetwear para andar, não para guardar",
  subtitle: "Camisetas, moletons e calças em tecido pesado, do P ao XGG",
  cta: { label: "Ver o drop atual", href: "/busca?ordem=newest" },
  secondary: { label: "Todas as peças", href: "/busca" },
};

async function featuredCollection(slug: string) {
  const [collection, products] = await Promise.all([
    collectionBySlug(slug),
    listProducts({ collection: slug }, { size: [], color: [], sort: "newest" }, undefined, PER_COLLECTION),
  ]);
  if (!collection.ok) return null;
  return { ...collection.data, products: products.ok ? products.data.items : [] };
}

function PoliciesStrip({ policies }: { policies: Policies }) {
  const items = [
    { icon: Truck, title: "Frete", text: policies.shipping_text },
    { icon: RefreshCcw, title: "Trocas", text: policies.returns_text },
    ...(policies.pix_discount_percent > 0
      ? [{ icon: QrCode, title: "Pix", text: `${policies.pix_discount_percent}% off no Pix` }]
      : []),
    ...(policies.max_installments > 1
      ? [
          {
            icon: CreditCard,
            title: "Parcelamento",
            text: `Em até ${policies.max_installments}x sem juros`,
          },
        ]
      : []),
  ];
  return (
    <section aria-labelledby="politicas" className="border-y border-ks-border py-8">
      <h2 id="politicas" className="sr-only">
        Políticas da loja
      </h2>
      <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {items.map(({ icon: Icon, title, text }) => (
          <li key={title} className="flex gap-3">
            <Icon aria-hidden className="mt-0.5 size-5 shrink-0 text-ks-fg" />
            <div className="space-y-1">
              <p className="text-sm font-semibold uppercase tracking-wide">{title}</p>
              <p className="text-sm text-ks-muted">{text}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default async function HomePage() {
  const [settings, arrivals] = await Promise.all([
    storeSettings(),
    listProducts({}, { size: [], color: [], sort: "newest" }, undefined, NEW_ARRIVALS),
  ]);
  const hero = settings
    ? {
        title: settings.hero.title,
        subtitle: settings.hero.subtitle,
        cta: { label: settings.hero.cta_label, href: safeNext(settings.hero.cta_href, "/busca") },
        secondary: {
          label: settings.secondary_cta.label,
          href: safeNext(settings.secondary_cta.href, "/busca"),
        },
        image: mediaUrl(settings.hero.image_key),
      }
    : { ...FALLBACK_HERO, image: null };
  const collections = (
    await Promise.all((settings?.featured_collection_slugs ?? []).map(featuredCollection))
  ).filter((collection) => collection !== null);
  const newest = arrivals.ok ? arrivals.data.items : [];

  return (
    <div className="space-y-16">
      <section aria-labelledby="hero" className="grid items-center gap-8 lg:grid-cols-2">
        <div className="space-y-6">
          <h1 id="hero" className="text-5xl leading-none sm:text-7xl">
            {hero.title}
          </h1>
          <p className="max-w-prose text-lg text-ks-muted">{hero.subtitle}</p>
          <div className="flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href={hero.cta.href}>{hero.cta.label}</Link>
            </Button>
            <Button asChild size="lg" variant="secondary">
              <Link href={hero.secondary.href}>{hero.secondary.label}</Link>
            </Button>
          </div>
        </div>
        {hero.image && (
          <div className="relative aspect-[4/5] overflow-hidden rounded-[var(--radius)] bg-ks-surface sm:aspect-[4/3] lg:aspect-[4/5]">
            <Image
              src={hero.image}
              alt=""
              fill
              priority
              sizes="(min-width: 1024px) 50vw, 100vw"
              className="object-cover"
            />
          </div>
        )}
      </section>

      {settings && <PoliciesStrip policies={settings.policies} />}

      {collections.map((collection) => (
        <section key={collection.slug} aria-labelledby={`colecao-${collection.slug}`} className="space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-ks-muted">Coleção</p>
              <h2 id={`colecao-${collection.slug}`} className="text-4xl">
                {collection.name}
              </h2>
              {collection.description && (
                <p className="max-w-prose text-sm text-ks-muted">{collection.description}</p>
              )}
            </div>
            <Link
              href={`/colecoes/${collection.slug}`}
              className="inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wide underline-offset-4 hover:underline"
            >
              Ver coleção
              <span className="sr-only"> {collection.name}</span>
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
          {collection.products.length > 0 ? (
            <ProductGrid products={collection.products} />
          ) : (
            <p className="text-sm text-ks-muted">Nenhuma peça nesta coleção no momento.</p>
          )}
        </section>
      ))}

      <section aria-labelledby="novidades" className="space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 id="novidades" className="text-4xl">
            Novidades
          </h2>
          <Link
            href="/busca?ordem=newest"
            className="inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wide underline-offset-4 hover:underline"
          >
            Ver todas
            <ArrowRight aria-hidden className="size-4" />
          </Link>
        </div>
        {newest.length > 0 ? (
          <ProductGrid products={newest} />
        ) : (
          <p className="text-sm text-ks-muted">As peças aparecem aqui assim que forem publicadas.</p>
        )}
      </section>
    </div>
  );
}
