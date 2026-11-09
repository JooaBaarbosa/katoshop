import type { CatalogComponents } from "@katoshop/api-client";

export type ProductDetail = CatalogComponents["schemas"]["ProductDetailOut"];
export type ProductImage = CatalogComponents["schemas"]["PublicImageOut"];
export type ProductVariant = CatalogComponents["schemas"]["PublicVariantOut"];
export type SizeState = "available" | "sold_out" | "absent";

export function findVariant(
  detail: ProductDetail,
  color: string | undefined,
  size: string | undefined,
): ProductVariant | undefined {
  return detail.variants.find((v) => v.color_code === color && v.size_code === size);
}

/** Estado de cada tamanho do produto na cor escolhida, na ordem dos tamanhos do detalhe. */
export function sizeStates(
  detail: ProductDetail,
  color: string,
): { code: string; label: string; state: SizeState }[] {
  return detail.sizes.map(({ code, label }) => {
    const variant = findVariant(detail, color, code);
    const state: SizeState = !variant ? "absent" : variant.available ? "available" : "sold_out";
    return { code, label, state };
  });
}

/** Fotos da cor primeiro, depois as genéricas (sem cor), cada grupo na ordem original. */
export function imagesForColor<T extends Pick<ProductImage, "color_code">>(
  images: T[],
  color: string,
): T[] {
  return [
    ...images.filter((image) => image.color_code === color),
    ...images.filter((image) => image.color_code === null),
  ];
}
