/** Estado que as actions de linha devolvem (o mesmo formato de `LineState`). */
export type LineErrorState = { ok: boolean; message?: string } | null;

/**
 * Erro de uma linha do carrinho com a versão da linha no render em que ele chegou.
 * - `version`: `lineVersion(item)` daquele render, ou seja, já com os dados do refresh que a
 *   action fez (`revalidatePath`), e não a versão que o formulário enviou;
 * - `cleared`: a linha mudou depois disso. É monotônico: o erro não volta se a versão retornar.
 */
export type TrackedLineError = {
  state: LineErrorState;
  version: string;
  cleared: boolean;
};

export const NO_LINE_ERROR: TrackedLineError = { state: null, version: "", cleared: false };

/**
 * Próximo estado do erro para o render atual. Devolve o mesmo objeto quando nada mudou, para o
 * componente só chamar `setState` (durante o render) quando precisa.
 */
export function trackLineError(
  prev: TrackedLineError,
  state: LineErrorState,
  version: string,
): TrackedLineError {
  if (state !== prev.state) return { state, version, cleared: false };
  if (!prev.state || prev.state.ok) return prev;
  if (!prev.cleared && version !== prev.version) return { ...prev, cleared: true };
  return prev;
}

export function visibleLineError(tracked: TrackedLineError): string | undefined {
  const { state, cleared } = tracked;
  return !cleared && state && !state.ok ? state.message : undefined;
}
