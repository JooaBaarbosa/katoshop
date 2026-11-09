import Image from "next/image";
import type { ProductImage } from "../lib/pdp";

/** Fotos da cor escolhida; só a primeira tem prioridade de carregamento. */
export function PdpGallery({ images, productName }: { images: ProductImage[]; productName: string }) {
  if (images.length === 0) {
    return (
      <div className="flex aspect-[4/5] items-center justify-center rounded-[var(--radius)] bg-ks-surface text-sm uppercase tracking-wide text-ks-muted">
        Sem foto de {productName}
      </div>
    );
  }
  return (
    <ul aria-label={`Fotos de ${productName}`} className="grid gap-3 sm:grid-cols-2">
      {images.map((image, index) => (
        <li key={image.url} className={index === 0 ? "sm:col-span-2" : undefined}>
          <figure className="space-y-1">
            <div className="relative aspect-[4/5] overflow-hidden rounded-[var(--radius)] bg-ks-surface">
              <Image
                src={image.url}
                alt={image.alt}
                fill
                priority={index === 0}
                sizes={
                  index === 0
                    ? "(min-width: 1024px) 58vw, 100vw"
                    : "(min-width: 1024px) 29vw, (min-width: 640px) 50vw, 100vw"
                }
                className="object-cover"
              />
            </div>
            {image.credit_author && (
              <figcaption className="text-xs text-ks-muted">
                Foto:{" "}
                {image.credit_source_url ? (
                  <a
                    href={image.credit_source_url}
                    rel="noopener noreferrer nofollow"
                    target="_blank"
                    className="underline underline-offset-2 hover:text-ks-fg"
                  >
                    {image.credit_author}
                  </a>
                ) : (
                  image.credit_author
                )}
                {image.license ? ` (${image.license})` : ""}
              </figcaption>
            )}
          </figure>
        </li>
      ))}
    </ul>
  );
}
