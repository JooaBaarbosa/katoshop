"use client";

import { Logo } from "@katoshop/ui/logo";
import { cn } from "@katoshop/ui/cn";
import {
  Activity,
  FolderTree,
  Layers,
  LayoutDashboard,
  LogOut,
  Package,
  ScrollText,
  ShoppingCart,
  Store,
  TicketPercent,
  Truck,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { logoutAction } from "../app/(painel)/actions";
import { isActive, NAV_ITEMS, type NavIcon } from "../lib/nav";

const ICONS: Record<NavIcon, LucideIcon> = {
  overview: LayoutDashboard,
  products: Package,
  categories: FolderTree,
  collections: Layers,
  orders: ShoppingCart,
  coupons: TicketPercent,
  shipping: Truck,
  customers: Users,
  storefront: Store,
  health: Activity,
  audit: ScrollText,
};

const ITEM = "flex items-center gap-3 rounded-[var(--radius)] px-3 py-2 text-sm";

/** Barra lateral escura (#0E0E0E) dentro do tema claro: o anel de foco volta a ser lima. */
export function Sidebar({ userName }: { userName: string }) {
  const pathname = usePathname();
  return (
    <aside className="flex flex-col gap-6 bg-admin-sidebar px-4 py-6 text-fg [--ks-focus:#d7ff3a] md:sticky md:top-0 md:h-dvh md:w-64 md:shrink-0 md:overflow-y-auto">
      <Link href="/" className="px-3" aria-label="Visão geral do painel KatoShop">
        <Logo tone="dark" aria-hidden />
      </Link>

      <nav aria-label="Painel" className="flex-1">
        <ul className="grid grid-cols-2 gap-1 md:grid-cols-1">
          {NAV_ITEMS.map((item) => {
            const Icon = ICONS[item.icon];
            if (item.href === undefined) {
              return (
                <li key={item.label}>
                  <span aria-disabled="true" className={cn(ITEM, "cursor-not-allowed text-muted")}>
                    <Icon aria-hidden className="size-4 shrink-0" />
                    <span className="flex-1">{item.label}</span>
                    <span className="border border-border px-1 font-mono text-[10px] uppercase">
                      {item.slice}
                    </span>
                  </span>
                </li>
              );
            }
            const active = isActive(pathname, item.href);
            return (
              <li key={item.label}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    ITEM,
                    "font-medium transition-colors duration-[var(--duration-fast)]",
                    active ? "bg-accent text-ks-accent-fg" : "text-fg hover:bg-surface",
                  )}
                >
                  <Icon aria-hidden className="size-4 shrink-0" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="space-y-2 border-t border-border pt-4">
        <p className="truncate px-3 text-sm text-muted">{userName}</p>
        <form action={logoutAction}>
          <button type="submit" className={cn(ITEM, "w-full text-fg hover:bg-surface")}>
            <LogOut aria-hidden className="size-4 shrink-0" />
            Sair
          </button>
        </form>
      </div>
    </aside>
  );
}
