import { expect, test } from "@playwright/test";
import { healVariant, SEED, seedPrice } from "./seed-reference";
import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  ADMIN_URL,
  addToCart,
  adminLogin,
  brl,
  openApi,
  staffToken,
} from "./support";

// Boné do seed com uma variante só (CNZ M). Começa e termina com o preço do seed (R26).
const BONE = SEED.boneCinzaM;

function priceInput(cents: number): string {
  return (cents / 100).toFixed(2).replace(".", ",");
}

test("preço alterado no admin aparece no carrinho do visitante em até 15 s", async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);
  const adminContext = await browser.newContext({ locale: "pt-BR" });
  try {
    const api = await openApi(adminContext);
    const token = await staffToken(api);
    // uma execução interrompida pode ter deixado outro preço: volta ao seed antes de começar
    const { productId } = await healVariant(api, token, BONE);
    try {
      const oldCents = seedPrice(BONE);
      const newCents = oldCents + 1000;
      await addToCart(page, BONE.slug, BONE.color, BONE.size);

      const admin = await adminContext.newPage();
      await adminLogin(admin, ADMIN_EMAIL, ADMIN_PASSWORD);
      await expect(admin).toHaveURL(`${ADMIN_URL}/`);
      await admin.goto(`${ADMIN_URL}/produtos/${productId}`);
      await admin.getByRole("tab", { name: "Variantes" }).click();
      await admin.getByLabel("Preço de Cinza mescla M em reais").fill(priceInput(newCents));
      await admin.getByRole("button", { name: "Salvar Cinza mescla M" }).click();
      // a grade recarrega com a versão nova e o preço salvo
      await expect(admin.getByLabel("Preço de Cinza mescla M em reais")).toHaveValue(
        priceInput(newCents),
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
      await healVariant(api, token, BONE, { log: false });
    }
  } finally {
    await adminContext.close();
  }
});
