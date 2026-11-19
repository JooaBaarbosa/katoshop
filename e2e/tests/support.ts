import { type BrowserContext, expect, type Locator, type Page } from "@playwright/test";

export const STORE_URL = process.env.E2E_STORE_URL ?? "http://katoshop.localhost";
export const ADMIN_URL = process.env.E2E_ADMIN_URL ?? "http://admin.katoshop.localhost";
export const API_URL = process.env.E2E_API_URL ?? "http://api.katoshop.localhost";

// Conta demo do bootstrap (Ruling R14); na CI vem do .env.example.
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@katoshop.localhost";
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "katoshop-demo-2026";

export type Customer = { name: string; email: string; password: string };

/** Cliente novo a cada execução: o volume local guarda as contas das execuções anteriores. */
export function newCustomer(tag: string): Customer {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  return {
    name: `Cliente ${tag} ${stamp}`,
    email: `cliente.${tag}.${stamp}@katoshop.localhost`,
    password: `e2e-${stamp}-senha-longa`,
  };
}

/** Cria a conta pela loja; termina em /conta, já logado. */
export async function registerCustomer(page: Page, customer: Customer): Promise<void> {
  await page.goto("/criar-conta");
  await page.getByLabel("Nome", { exact: true }).fill(customer.name);
  await page.getByLabel("Email", { exact: true }).fill(customer.email);
  await page.getByLabel("Senha", { exact: true }).fill(customer.password);
  await page.getByRole("button", { name: "Criar conta" }).click();
  await expect(page).toHaveURL(/\/conta$/);
}

/** Entra no painel com a conta demo (formulário de /entrar do admin). */
export async function adminLogin(page: Page, email: string, password: string): Promise<void> {
  await page.goto(`${ADMIN_URL}/entrar`);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}

// ---------------------------------------------------------------------------- carrinho

/** Mesmo formato do formatBRL da loja (Intl pt-BR), para comparar valores da tela. */
export function brl(cents: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(cents / 100);
}

/**
 * Adiciona uma variante pela página de produto. Com JavaScript espera o toast; sem ele, o
 * formulário posta a action e a página volta renderizada pelo servidor.
 */
export async function addToCart(
  page: Page,
  slug: string,
  color: string,
  size: string,
  jsEnabled = true,
): Promise<void> {
  await page.goto(`/p/${slug}?cor=${color}&tamanho=${size}`);
  const button = page.getByRole("button", { name: "Adicionar ao carrinho" });
  await expect(button).toBeEnabled();
  if (jsEnabled) {
    await button.click();
    await expect(page.getByText("Adicionado ao carrinho")).toBeVisible();
  } else {
    await Promise.all([page.waitForEvent("load"), button.click()]);
    await expect(page.getByRole("button", { name: "Adicionar ao carrinho" })).toBeVisible();
  }
}

/** Linha do /carrinho pelo nome do produto. */
export function cartLine(page: Page, name: string): Locator {
  return page
    .getByRole("region", { name: "Itens do carrinho" })
    .getByRole("listitem")
    .filter({
      has: page.getByRole("heading", { level: 2, name, exact: true }),
    });
}

/**
 * Espera a quantidade da linha conferindo antes o erro da linha (o `p[role=status]`; o
 * `<output>` da quantidade também tem papel status). Se a ação falhar, o timeout mostra a
 * mensagem de erro da tela, não só a quantidade antiga.
 */
export async function expectQuantity(line: Locator, quantity: number): Promise<void> {
  const error = line.locator('p[role="status"]');
  const output = line.getByLabel("Quantidade", { exact: true });
  await expect(async () => {
    expect(await error.textContent(), "erro da linha do carrinho").toBe("");
    expect(await output.textContent(), "quantidade da linha").toBe(String(quantity));
  }).toPass({ timeout: 10_000 });
}

/** Valor de uma linha do resumo (Subtotal, Desconto ou Total). */
export function summaryValue(page: Page, label: string): Locator {
  return page
    .getByRole("complementary", { name: "Resumo do pedido" })
    .locator("dt", { hasText: new RegExp(`^${label}$`) })
    .locator("+ dd");
}

/** Clica e, sem JavaScript, espera a página nova (o formulário faz um POST de página inteira). */
export async function submit(page: Page, target: Locator, jsEnabled: boolean): Promise<void> {
  if (jsEnabled) await target.click();
  else await Promise.all([page.waitForEvent("load"), target.click()]);
}

// ---------------------------------------------------------------------------- API pelo navegador

export type ApiResponse<T> = { status: number; body: T };

export type Api = {
  call<T = unknown>(
    method: string,
    path: string,
    options?: {
      token?: string;
      body?: unknown;
      headers?: Record<string, string>;
    },
  ): Promise<ApiResponse<T>>;
  close(): Promise<void>;
};

/**
 * Chamadas ao gateway feitas por uma página na origem da API: o Chromium resolve *.localhost
 * e o Node no Windows não (o request do Playwright roda no Node).
 */
export async function openApi(context: BrowserContext): Promise<Api> {
  const page = await context.newPage();
  // qualquer resposta serve: só precisa de um documento na origem da API
  await page.goto(`${API_URL}/catalog/v1/products/camiseta-pesada-preta`);
  return {
    async call<T>(
      method: string,
      path: string,
      options: {
        token?: string;
        body?: unknown;
        headers?: Record<string, string>;
      } = {},
    ): Promise<ApiResponse<T>> {
      const raw = await page.evaluate(
        async ({ method, url, token, body, headers }) => {
          const all: Record<string, string> = { ...headers };
          if (token) all.Authorization = `Bearer ${token}`;
          if (body !== undefined) all["Content-Type"] = "application/json";
          const response = await fetch(url, {
            method,
            headers: all,
            body: body === undefined ? undefined : JSON.stringify(body),
          });
          return { status: response.status, text: await response.text() };
        },
        {
          method,
          url: `${API_URL}${path}`,
          token: options.token,
          body: options.body,
          headers: options.headers ?? {},
        },
      );
      let body: unknown = raw.text || null;
      try {
        body = raw.text ? JSON.parse(raw.text) : null;
      } catch {
        // corpo que não é JSON (ex.: 400 do Traefik) fica como texto
      }
      return { status: raw.status, body: body as T };
    },
    close: () => page.close(),
  };
}

/** Token de funcionário da conta demo (uma chamada: o login tem limite de taxa no gateway). */
export async function staffToken(api: Api): Promise<string> {
  const response = await api.call<{ access_token: string }>(
    "POST",
    "/identity/v1/auth/staff/login",
    { body: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } },
  );
  expect(response.status).toBe(200);
  return response.body.access_token;
}

export type AdminVariant = {
  id: string;
  color_code: string;
  size_code: string;
  price_cents: number | null;
  effective_price_cents: number;
  stock_on_hand: number;
  available: number;
  version: number;
};

/** Produto do seed (id e variantes) pela API de admin do catálogo. */
export async function adminProduct(
  api: Api,
  token: string,
  slug: string,
): Promise<{ id: string; variants: AdminVariant[] }> {
  const list = await api.call<{ items: { id: string; slug: string }[] }>(
    "GET",
    `/catalog/v1/admin/products?slug=${slug}`,
    { token },
  );
  const match = list.body.items.find((item) => item.slug === slug);
  if (!match) throw new Error(`produto ${slug} não encontrado; rode pnpm seed`);
  const detail = await api.call<{ id: string; variants: AdminVariant[] }>(
    "GET",
    `/catalog/v1/admin/products/${match.id}`,
    { token },
  );
  return detail.body;
}

export function variantOf(
  product: { variants: AdminVariant[] },
  color: string,
  size: string,
): AdminVariant {
  const variant = product.variants.find((v) => v.color_code === color && v.size_code === size);
  if (!variant) throw new Error(`variante ${color} ${size} não encontrada`);
  return variant;
}

/** Ajuste de estoque pela API de admin (reason "adjustment"). */
export async function adjustStock(
  api: Api,
  token: string,
  variantId: string,
  delta: number,
  note: string,
): Promise<void> {
  const response = await api.call(
    "POST",
    `/catalog/v1/admin/variants/${variantId}/stock-adjustments`,
    {
      token,
      body: { delta, reason: "adjustment", note },
    },
  );
  expect(response.status).toBe(201);
}

/** Carrinho de visitante pela API do cart, com o id do cookie ks_cart da loja. */
export async function guestCart(
  api: Api,
  context: BrowserContext,
): Promise<{
  items: { variant_id: string; quantity: number; available: number }[];
}> {
  const cookies = await context.cookies(STORE_URL);
  const cartId = cookies.find((cookie) => cookie.name === "ks_cart")?.value;
  if (!cartId) throw new Error("sem cookie ks_cart: o visitante ainda não tem carrinho");
  const response = await api.call<{
    items: { variant_id: string; quantity: number; available: number }[];
  }>("GET", "/cart/v1/cart", { headers: { "X-Cart-Id": cartId } });
  expect(response.status).toBe(200);
  return response.body;
}
