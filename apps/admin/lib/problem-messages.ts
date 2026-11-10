import { ApiProblem } from "@katoshop/api-client";

/** Textos pt-BR dos códigos de problema do catálogo e dos blockers de publicação. */
const MESSAGES: Record<string, string> = {
  "catalog.product.version_conflict":
    "Este produto foi alterado por outra pessoa. Recarregue para ver a versão atual.",
  "catalog.product.slug_taken": "Já existe um produto com este endereço.",
  "catalog.product.invalid_slug": "Use só letras minúsculas, números e hífens no endereço.",
  "catalog.product.not_found": "Produto não encontrado.",
  "catalog.product.not_publishable": "O produto ainda não pode ser publicado.",
  "catalog.variant.version_conflict":
    "Esta variante foi alterada por outra pessoa. Recarregue para ver a versão atual.",
  "catalog.variant.not_found": "Variante não encontrada.",
  "catalog.variant.unknown_option": "Escolha cores e tamanhos da lista.",
  "catalog.stock.would_go_negative": "O estoque não pode ficar negativo.",
  "catalog.stock.zero_delta": "Informe uma quantidade diferente de zero.",
  "catalog.stock.invalid_reason": "Escolha um motivo válido.",
  "catalog.image.too_large": "A imagem passa de 8 MB.",
  "catalog.image.unsupported_type": "Envie JPG, PNG ou WebP.",
  "catalog.image.alt_required": "Descreva a imagem no texto alternativo.",
  "catalog.image.unknown_color": "Escolha uma cor da lista.",
  "catalog.image.not_found": "Foto não encontrada.",
  "catalog.category.in_use": "Há produtos nesta categoria.",
  "catalog.category.parent_cycle":
    "Uma categoria não pode ficar dentro dela mesma nem de uma subcategoria sua.",
  "catalog.category.slug_taken": "Já existe uma categoria com este endereço.",
  "catalog.category.invalid_slug": "Use só letras minúsculas, números e hífens no endereço.",
  "catalog.category.not_found": "Categoria não encontrada.",
  "catalog.collection.slug_taken": "Já existe uma coleção com este endereço.",
  "catalog.collection.invalid_slug": "Use só letras minúsculas, números e hífens no endereço.",
  "catalog.collection.duplicate_product": "Um produto aparece mais de uma vez na coleção.",
  "catalog.collection.not_found": "Coleção não encontrada.",
  "catalog.pagination.invalid_cursor": "A página pedida não existe mais. Volte ao início da lista.",
  "catalog.search.query_too_long": "A busca aceita no máximo 200 caracteres.",
  "request.validation": "Confira os campos destacados.",
  "http.429": "Muitas ações seguidas. Aguarde um instante e tente de novo.",
  // blockers de publicação (errors.product do 422 catalog.product.not_publishable)
  no_active_variant: "Ative pelo menos uma variante de cor e tamanho.",
  no_image: "Envie pelo menos uma foto.",
  no_price: "Toda variante ativa precisa de preço maior que zero.",
};

export function messageFor(code: string, traceId?: string): string {
  const known = MESSAGES[code];
  if (known !== undefined) return known;
  return traceId
    ? `Algo deu errado. Código para suporte: ${traceId}`
    : "Algo deu errado. Tente de novo em instantes.";
}

/** Mensagem de qualquer erro de chamada à API (falha de rede vira o texto genérico). */
export function problemMessage(error: unknown): string {
  if (!(error instanceof ApiProblem)) return messageFor("");
  if (error.status === 429) return messageFor("http.429");
  return messageFor(error.code, error.traceId);
}

/** Pendências de publicação em pt-BR, lidas de `errors.product`. */
export function blockerMessages(error: ApiProblem): string[] {
  return (error.errors?.product ?? []).map((code) => messageFor(code));
}
