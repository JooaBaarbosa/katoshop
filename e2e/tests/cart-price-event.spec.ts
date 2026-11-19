import { expect, test } from "@playwright/test";
import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  ADMIN_URL,
  addToCart,
  adminLogin,
  adminProduct,
  brl,
  openApi,
  staffToken,
  variantOf,
} from "./support";

// Boné do seed com uma variante só (CNZ M). O preço volta ao original no fim (R26).
const SLUG = "bone-lavado-cinza";

test("preço alterado no admin aparece no carrinho do visitante em até 15 s", async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);
  await addToCart(page, SLUG, "CNZ", "M");

  const adminContext = await browser.newContext({ locale: "pt-BR" });
  const api = await openApi(adminContext);
  const token = await staffToken(api);
  const product = await adminProduct(api, token, SLUG);
  const original = variantOf(product, "CNZ", "M");
  const oldCents = original.effective_price_cents;
  const newCents = oldCents + 1000;

  try {
    const admin = await adminContext.newPage();
    await adminLogin(admin, ADMIN_EMAIL, ADMIN_PASSWORD);
    await expect(admin).toHaveURL(`${ADMIN_URL}/`);
    await admin.goto(`${ADMIN_URL}/produtos/${product.id}`);
    await admin.getByRole("tab", { name: "Variantes" }).click();
    const price = admin.getByLabel("Preço de Cinza mescla M em reais");
    await price.fill((newCents / 100).toFixed(2).replace(".", ","));
    await admin.getByRole("button", { name: "Salvar Cinza mescla M" }).click();
    // a grade recarrega com a versão nova e o preço salvo
    await expect(admin.getByLabel("Preço de Cinza mescla M em reais")).toHaveValue(
      (newCents / 100).toFixed(2).replace(".", ","),
    );

    // outbox, RabbitMQ e consumidor do cart: critério de 5 s com folga para a CI
    const notice = page.getByText(`O preço mudou de ${brl(oldCents)} para ${brl(newCents)}.`);
    await expect
      .poll(
        async () => {
          await page.goto("/carrinho");
          return notice.count();
        },
        { timeout: 15_000, intervals: [500, 1_000] },
      )
      .toBe(1);
  } finally {
    // devolve o preço exato do seed (null = herda o preço base), com a versão atual
    const current = variantOf(await adminProduct(api, token, SLUG), "CNZ", "M");
    const restored = await api.call("PATCH", `/catalog/v1/admin/variants/${current.id}`, {
      token,
      body: { version: current.version, price_cents: original.price_cents },
    });
    expect(restored.status).toBe(200);
    await adminContext.close();
  }
});
