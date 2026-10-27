import { Logo } from "@katoshop/ui/logo";
import Link from "next/link";
import { DEMO_NOTICE_FALLBACK, type Policies } from "../lib/storefront";

const LEGAL_LINKS = [
  { href: "/privacidade", label: "Privacidade" },
  { href: "/termos", label: "Termos" },
  { href: "/creditos", label: "Créditos" },
];

export function SiteFooter({ policies }: { policies: Policies | null }) {
  return (
    <footer className="mt-16 border-t border-ks-border text-sm text-ks-muted">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 md:grid-cols-3">
        <div className="space-y-3">
          <Logo tone="dark" className="h-6" />
          <p>Streetwear em tecido pesado, do P ao XGG.</p>
        </div>

        {policies ? (
          <dl className="space-y-3">
            <div>
              <dt className="font-semibold uppercase tracking-wide text-ks-fg">Frete</dt>
              <dd>{policies.shipping_text}</dd>
            </div>
            <div>
              <dt className="font-semibold uppercase tracking-wide text-ks-fg">Trocas</dt>
              <dd>{policies.returns_text}</dd>
            </div>
          </dl>
        ) : (
          <div />
        )}

        <nav aria-label="Institucional">
          <ul className="space-y-2">
            {LEGAL_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="transition-colors duration-[var(--duration-fast)] hover:text-ks-fg"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <p className="border-t border-ks-border px-4 py-4 text-center font-mono text-xs uppercase tracking-wide">
        {policies?.demo_notice || DEMO_NOTICE_FALLBACK}
      </p>
    </footer>
  );
}
