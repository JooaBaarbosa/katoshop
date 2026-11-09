import type { Metadata } from "next";
import Image from "next/image";
import { safeHttpUrl } from "../../../lib/credits";
import { photoCredits } from "../../../lib/storefront";

export const metadata: Metadata = {
  title: "Créditos das fotos",
  description: "Autores, origem e licença das fotos usadas na KatoShop.",
  alternates: { canonical: "/creditos" },
};

export default async function CreditsPage() {
  const result = await photoCredits();
  if (!result.ok) throw new Error("Catálogo indisponível ao carregar os créditos");
  const credits = result.data;

  return (
    <section className="space-y-6">
      <h1 className="text-5xl">Créditos das fotos</h1>
      <p className="max-w-prose text-sm text-ks-muted">
        As fotos de produto são imagens reais com licença livre. Cada uma está creditada abaixo.
      </p>

      {credits.length === 0 ? (
        <p className="border border-ks-border bg-ks-surface p-4 text-sm">
          Ainda não há fotos com crédito cadastrado.
        </p>
      ) : (
        <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {credits.map((credit) => {
            const source = safeHttpUrl(credit.credit_source_url);
            const author = credit.credit_author ?? "Autor não informado";
            return (
              <li key={`${credit.product_name}-${credit.image_url}`} className="flex gap-4">
                <Image
                  src={credit.image_url}
                  alt={`Foto de ${credit.product_name}`}
                  width={96}
                  height={120}
                  className="h-30 w-24 shrink-0 rounded-[var(--radius)] bg-ks-surface object-cover"
                />
                <div className="space-y-1 text-sm">
                  <h2 className="font-sans text-sm font-semibold normal-case">
                    {credit.product_name}
                  </h2>
                  <p>
                    Autor:{" "}
                    {source ? (
                      <a
                        href={source}
                        rel="noopener noreferrer"
                        target="_blank"
                        className="underline underline-offset-4"
                      >
                        {author}
                      </a>
                    ) : (
                      author
                    )}
                  </p>
                  {credit.license && <p className="text-ks-muted">Licença: {credit.license}</p>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
