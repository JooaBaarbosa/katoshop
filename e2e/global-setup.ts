import { chromium, expect, type FullConfig, type Page } from "@playwright/test";

/**
 * Aquecimento da pilha antes dos specs: com os containers recém-subidos, a primeira chamada a
 * cada caminho (SSR do /carrinho, token de serviço do cart, leitura interna da variante no
 * catalog, evaluate do promotions) pode passar do timeout curto entre serviços e falhar o
 * primeiro spec. Aqui um visitante descartável abre o /carrinho, adiciona um item, aplica o
 * cupom demo e desfaz tudo. Usa o navegador porque o Node no Windows não resolve *.localhost.
 */
const PRODUCT = { slug: "camiseta-pesada-branca", name: "Camiseta pesada branca" };
const ATTEMPTS = 3;
// fora do runner o expect não lê o timeout do playwright.config
const slow = expect.configure({ timeout: 30_000 });

async function warmUp(page: Page): Promise<void> {
  await page.goto("/carrinho");
  await slow(page.locator("#carrinho-titulo")).toBeVisible();

  // escrita no carrinho: cart -> identity (token de serviço) -> catalog (variante interna)
  await page.goto(`/p/${PRODUCT.slug}?cor=BRC&tamanho=M`);
  await page.getByRole("button", { name: "Adicionar ao carrinho" }).click();
  await slow(page.getByText("Adicionado ao carrinho")).toBeVisible();

  // avaliação do cupom: cart -> promotions; qualquer resposta (desconto ou motivo) serve
  await page.goto("/carrinho");
  await page.getByLabel("Cupom", { exact: true }).fill("BEMVINDO10");
  await page.getByRole("button", { name: "Aplicar" }).click();
  const removeCoupon = page.getByRole("button", { name: "Remover cupom" });
  await slow(
    removeCoupon.or(page.locator("#coupon-status").filter({ hasText: /\S/ })),
  ).toBeVisible();

  // limpeza: tira o cupom (se ficou) e o item; o carrinho vazio do visitante expira sozinho
  if (await removeCoupon.isVisible()) {
    await removeCoupon.click();
    await slow(page.getByLabel("Cupom", { exact: true })).toBeVisible();
  }
  const line = page
    .getByRole("region", { name: "Itens do carrinho" })
    .getByRole("listitem")
    .filter({ has: page.getByRole("heading", { level: 2, name: PRODUCT.name, exact: true }) });
  await line.getByRole("button", { name: "Remover", exact: true }).click();
  await slow(page.getByText("Seu carrinho está vazio.")).toBeVisible();
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  const use = config.projects[0]?.use ?? {};
  const browser = await chromium.launch({ channel: use.channel });
  try {
    for (let attempt = 1; ; attempt++) {
      const context = await browser.newContext({ baseURL: use.baseURL, locale: use.locale });
      const page = await context.newPage();
      page.setDefaultTimeout(30_000);
      try {
        await warmUp(page);
        return;
      } catch (error) {
        if (attempt >= ATTEMPTS) throw error;
        console.warn(`aquecimento da pilha falhou (tentativa ${attempt}); tentando de novo`);
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}
