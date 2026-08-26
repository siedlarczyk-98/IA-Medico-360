/**
 * Regra de teclado dos campos de envio do chat.
 *
 * Vive num só lugar porque dois componentes a usam (InputBar e
 * ClarificationPrompt) e uma cópia divergente daria a dois campos vizinhos
 * comportamentos diferentes para a mesma tecla.
 *
 * - Enter envia (desktop)
 * - Shift + Enter quebra linha
 * - Ctrl/Cmd + Enter envia, preservando o atalho antigo de quem já o usava
 * - No mobile, Enter quebra linha: o Enter do teclado virtual é usado para
 *   parágrafo, e enviar ali partiria caso clínico longo a cada nova linha
 * - Enter durante composição de IME confirma o caractere, não envia
 */
export function tratarEnterParaEnviar(
  e: React.KeyboardEvent,
  opcoes: { isMobile: boolean; submit: () => void },
): void {
  const { isMobile, submit } = opcoes;
  if (e.key !== 'Enter') return;
  if (e.nativeEvent.isComposing) return;
  if (e.metaKey || e.ctrlKey) { e.preventDefault(); submit(); return; }
  if (e.shiftKey) return;
  if (isMobile) return;
  e.preventDefault();
  submit();
}

/** Dica exibida ao lado do botão de envio. Vazia no mobile, que não tem atalho. */
export const DICA_ENVIO = '⏎ enviar · ⇧ + ⏎ quebrar linha';
