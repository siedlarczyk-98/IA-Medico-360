/**
 * Qual casca montar — desktop ou mobile — na MESMA URL.
 *
 * POR QUE NA MESMA URL
 * A Waid tem um link só para o Médico 360, que abre tanto no app nativo quanto
 * no site (dentro de um iframe). Não existe "link do celular". A decisão é
 * tomada aqui, na hora, pelo espaço disponível.
 *
 * POR QUE ESPAÇO E NÃO APARELHO
 * O user-agent do webview da Waid se anuncia como Chrome mobile, tablets mentem
 * nos dois sentidos, e dentro do iframe o que importa é a largura do IFRAME, não
 * a do aparelho. Largura, altura e tipo de ponteiro respondem à pergunta certa:
 * "cabe o layout de desktop aqui?".
 *
 * HISTERESE
 * Existe uma faixa em que nenhuma casca é forçada, e ali vale a que já estava.
 * Sem isso, um celular deitado (844–932 px de largura) viraria desktop no meio
 * da leitura, e uma janela arrastada perto do limite ficaria piscando entre as
 * duas. O celular deitado tem regra própria: é largo, mas é baixo e de dedo.
 *
 * FLAG E OVERRIDE
 * `VITE_SHELL_MOVEL` = `off` (padrão: sempre desktop), `qa` (desktop, a menos
 * que `?layout=` peça outra) ou `on` (automático). O `?layout=mobile|desktop|auto`
 * vale em qualquer rota e fica na sessionStorage: o link de embed entra por
 * `/embed-auth`, que redireciona e perde a query. SessionStorage e não
 * localStorage porque o webview da Waid guarda o localStorage para sempre, e um
 * override de teste grudaria num médico de verdade.
 *
 * Store de módulo lido com `useSyncExternalStore`: sem `useState` + efeito, que
 * renderizaria duas vezes a cada rotação.
 */

import { useSyncExternalStore } from 'react';

export type Layout = 'desktop' | 'mobile';
type Flag = 'off' | 'qa' | 'on';
type Override = Layout | 'auto';

const CHAVE_OVERRIDE = 'm360_layout';
/** A rotação dispara uma rajada de `resize`; decide-se uma vez, no fim dela. */
const ESPERA_MS = 150;
/** Limite da regra antiga de `useIsMobile`, válida enquanto a flag está desligada. */
const LIMITE_LEGADO = 768;

// ── Regras ────────────────────────────────────────────────────────────────

function consulta(q: string): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(q).matches;
}

/** Celular deitado: largo, mas baixo e de dedo. Nunca é desktop. */
const celularDeitado = () => consulta('(pointer: coarse) and (max-height: 500px)');

function forcaMobile(): boolean {
  return consulta('(max-width: 720px)')
    || celularDeitado()
    || consulta('(pointer: coarse) and (orientation: portrait) and (max-width: 860px)');
}

function forcaDesktop(): boolean {
  return consulta('(min-width: 820px)') && consulta('(min-height: 501px)') && !celularDeitado();
}

/** A decisão automática, com histerese: na faixa do meio, fica o anterior. */
export function decidirLayout(anterior: Layout | null): Layout {
  if (forcaMobile()) return 'mobile';
  if (forcaDesktop()) return 'desktop';
  return anterior ?? 'desktop';
}

// ── Flag e override ───────────────────────────────────────────────────────

function flag(): Flag {
  const v = import.meta.env.VITE_SHELL_MOVEL;
  return v === 'on' || v === 'qa' ? v : 'off';
}

/** A casca mobile pode ser montada nesta build (pelo automático ou por override)? */
export function cascaMovelDisponivel(): boolean {
  return flag() !== 'off';
}

function lerOverride(): Override | null {
  try {
    const daUrl = new URLSearchParams(window.location.search).get('layout');
    if (daUrl === 'mobile' || daUrl === 'desktop' || daUrl === 'auto') {
      sessionStorage.setItem(CHAVE_OVERRIDE, daUrl);
      return daUrl;
    }
    const salvo = sessionStorage.getItem(CHAVE_OVERRIDE);
    return salvo === 'mobile' || salvo === 'desktop' || salvo === 'auto' ? salvo : null;
  } catch {
    // Storage bloqueado (webview restrito, aba privada): sem override.
    return null;
  }
}

// ── Store ─────────────────────────────────────────────────────────────────

let automatico: Layout = 'desktop';
let override: Override | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
const ouvintes = new Set<() => void>();

/** A casca que vale agora, depois da flag e do override. */
function efetivo(): Layout {
  const f = flag();
  if (f === 'off') return 'desktop';
  if (override === 'mobile' || override === 'desktop') return override;
  if (f === 'qa' && override !== 'auto') return 'desktop';
  return automatico;
}

function avisar() {
  for (const fn of ouvintes) fn();
}

function reavaliar() {
  timer = null;
  const antes = efetivo();
  automatico = decidirLayout(automatico);
  if (efetivo() !== antes) avisar();
}

function aoRedimensionar() {
  // O `useIsMobile` legado acompanha a largura sem espera, como antes.
  avisar();
  if (timer !== null) clearTimeout(timer);
  timer = setTimeout(reavaliar, ESPERA_MS);
}

function assinar(fn: () => void): () => void {
  ouvintes.add(fn);
  if (ouvintes.size === 1) {
    // Sem ninguém ouvindo, os `resize` passaram batido: atualiza antes de ouvir.
    automatico = decidirLayout(automatico);
    window.addEventListener('resize', aoRedimensionar);
    window.addEventListener('orientationchange', aoRedimensionar);
  }
  return () => {
    ouvintes.delete(fn);
    if (ouvintes.size === 0) {
      window.removeEventListener('resize', aoRedimensionar);
      window.removeEventListener('orientationchange', aoRedimensionar);
    }
  };
}

/** Recalcula tudo do zero. Roda ao carregar o módulo — sem flash de desktop no celular. */
export function reiniciarLayout(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  override = lerOverride();
  automatico = decidirLayout(null);
  avisar();
}

/** Só para testes: aplica agora a decisão que esperaria o fim da rajada de `resize`. */
export function aplicarLayoutAgora(): void {
  if (timer !== null) clearTimeout(timer);
  reavaliar();
}

reiniciarLayout();

// ── Hooks ─────────────────────────────────────────────────────────────────

export function useLayout(): Layout {
  return useSyncExternalStore(assinar, efetivo, efetivo);
}

/**
 * "Estou apertado?" — o que os componentes usam para ajustes de tamanho.
 *
 * Com a casca mobile ligada, segue a casca: dentro dela é sempre `true`, e na
 * de desktop sempre `false`, mesmo na faixa da histerese. Desligada, vale a
 * regra de antes (largura ≤ 768), para nada mudar para quem já usa.
 */
function compacto(): boolean {
  if (flag() === 'off') return window.innerWidth <= LIMITE_LEGADO;
  return efetivo() === 'mobile';
}

export function useCompacto(): boolean {
  return useSyncExternalStore(assinar, compacto, compacto);
}
