export type NavIcon =
  | "overview"
  | "products"
  | "categories"
  | "collections"
  | "orders"
  | "coupons"
  | "shipping"
  | "customers"
  | "storefront"
  | "health"
  | "audit";

export type NavItem = {
  label: string;
  icon: NavIcon;
  /** Ausente: a seção ainda não existe e aparece desabilitada. */
  href?: string;
  /** Fatia em que a seção desabilitada chega. */
  slice?: string;
};

export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Visão geral", href: "/", icon: "overview" },
  { label: "Produtos", href: "/produtos", icon: "products" },
  { label: "Categorias", href: "/categorias", icon: "categories" },
  { label: "Coleções", href: "/colecoes", icon: "collections" },
  { label: "Pedidos", slice: "Fatia 3", icon: "orders" },
  { label: "Cupons", slice: "Fatia 2", icon: "coupons" },
  { label: "Frete", slice: "Fatia 3", icon: "shipping" },
  { label: "Clientes", slice: "Fatia 4", icon: "customers" },
  { label: "Vitrine", slice: "Fatia 4", icon: "storefront" },
  { label: "Saúde do sistema", slice: "Fatia 4", icon: "health" },
  { label: "Auditoria", slice: "Fatia 4", icon: "audit" },
];

/** A raiz só casa com ela mesma; as seções casam também com as subpáginas. */
export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
