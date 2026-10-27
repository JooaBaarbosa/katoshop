import { Logo } from "@katoshop/ui/logo";
import { Search, ShoppingBag, User } from "lucide-react";
import Link from "next/link";
import type { PublicCategory } from "../lib/storefront";

const ACTION =
  "inline-flex h-9 items-center gap-2 rounded-[var(--radius)] px-2 text-sm font-semibold uppercase tracking-wide";

export function SiteHeader({ categories }: { categories: PublicCategory[] }) {
  return (
    <header className="border-b border-ks-border">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-4">
        <Link href="/" aria-label="KatoShop, página inicial" className="shrink-0">
          <Logo tone="dark" className="h-7" />
        </Link>

        {categories.length > 0 && (
          <nav aria-label="Categorias" className="order-last w-full md:order-none md:w-auto">
            <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm font-semibold uppercase tracking-wide">
              {categories.map((category) => (
                <li key={category.slug}>
                  <Link
                    href={`/c/${category.slug}`}
                    className="text-ks-muted transition-colors duration-[var(--duration-fast)] hover:text-ks-fg"
                  >
                    {category.name}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        )}

        <form action="/busca" role="search" className="ml-auto flex items-center">
          <label htmlFor="site-search" className="sr-only">
            Buscar peças
          </label>
          <input
            id="site-search"
            type="search"
            name="q"
            maxLength={200}
            placeholder="Buscar"
            className="h-9 w-36 rounded-[var(--radius)] border border-ks-border bg-ks-surface px-3 text-sm text-ks-fg placeholder:text-ks-muted sm:w-52"
          />
          <button
            type="submit"
            aria-label="Buscar"
            className="ml-1 inline-flex size-9 items-center justify-center rounded-[var(--radius)] text-ks-fg transition-colors duration-[var(--duration-fast)] hover:bg-ks-fg/10"
          >
            <Search aria-hidden className="size-4" />
          </button>
        </form>

        <div className="flex items-center gap-1">
          <Link
            href="/conta"
            className={`${ACTION} transition-colors duration-[var(--duration-fast)] hover:bg-ks-fg/10`}
          >
            <User aria-hidden className="size-4" />
            Conta
          </Link>
          <button
            type="button"
            disabled
            title="Disponível na próxima versão"
            className={`${ACTION} cursor-not-allowed text-ks-muted`}
          >
            <ShoppingBag aria-hidden className="size-4" />
            Carrinho
          </button>
        </div>
      </div>
    </header>
  );
}
