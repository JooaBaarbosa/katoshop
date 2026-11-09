// Mesma regra de caminho interno da Ruling R11: uma barra inicial não seguida de "/" ou "\",
// sem "\" nem espaços ou caracteres de controle em lugar nenhum.
// eslint-disable-next-line no-control-regex -- recusar caracteres de controle é o objetivo
const INTERNAL_PATH = /^\/([^/\\\x00-\x20\x7f][^\\\x00-\x20\x7f]*)?$/;

/** Destino pós-login: só caminhos internos; qualquer outra coisa vira o fallback. */
export function safeNext(value: FormDataEntryValue | string | null | undefined, fallback = "/") {
  return typeof value === "string" && INTERNAL_PATH.test(value) ? value : fallback;
}
