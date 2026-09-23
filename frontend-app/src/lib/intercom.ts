// Integração Intercom via snippet oficial (vanilla), fora do ciclo de vida do
// React. Inicializa uma única vez no carregamento — assim o launcher não pisca
// nem some com re-renders/StrictMode, ao contrário do wrapper react-use-intercom.

type IntercomFn = ((...args: unknown[]) => void) & { q?: unknown[]; c?: (a: unknown) => void };

declare global {
  interface Window {
    Intercom?: IntercomFn;
    intercomSettings?: Record<string, unknown>;
  }
}

let loaded = false;

/**
 * Tela de telefone: o mesmo corte dos tokens (`shared/design/tokens.css`).
 *
 * No celular o balão padrão do Intercom fica no canto inferior direito — em
 * cima do botão Enviar, o mais usado do app. Subir o balão o poria flutuando
 * sobre o texto da resposta. Ele fica escondido no telefone, e o suporte passa
 * a abrir pelo menu (`abrirSuporte`), como em qualquer app com campo de
 * digitação embaixo.
 */
const TELEFONE = '(max-width: 768px)';

function launcherEscondido(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(TELEFONE).matches;
}

/** O suporte está disponível nesta sessão? (o widget só carrega com `app_id`) */
export function suporteDisponivel(): boolean {
  return loaded;
}

/** Abre o Messenger. É o caminho do suporte quando o balão está escondido. */
export function abrirSuporte(): void {
  window.Intercom?.('show');
}

/** Carrega o widget e dá boot anônimo. Chamar uma vez, no startup. */
export function loadIntercom(appId: string): void {
  if (!appId || loaded || typeof window === 'undefined') return;
  loaded = true;

  window.intercomSettings = { app_id: appId, hide_default_launcher: launcherEscondido() };

  // Girar o aparelho ou redimensionar a janela atravessa o corte: o balão
  // aparece e some junto com o layout.
  if (typeof window.matchMedia === 'function') {
    window.matchMedia(TELEFONE).addEventListener?.('change', e => {
      window.Intercom?.('update', { hide_default_launcher: e.matches });
    });
  }

  const w = window;
  const ic = w.Intercom;
  if (typeof ic === 'function') {
    ic('reattach_activator');
    ic('update', w.intercomSettings);
    return;
  }

  const i: IntercomFn = function (...args: unknown[]) {
    i.c?.(args);
  };
  i.q = [];
  i.c = (args: unknown) => { i.q!.push(args); };
  w.Intercom = i;

  const load = () => {
    const s = document.createElement('script');
    s.type = 'text/javascript';
    s.async = true;
    s.src = `https://widget.intercom.io/widget/${appId}`;
    const x = document.getElementsByTagName('script')[0];
    x.parentNode?.insertBefore(s, x);
  };

  if (document.readyState === 'complete') load();
  else w.addEventListener('load', load, false);
}

/**
 * Identifica o usuário logado. Quando o Messenger Security está ativo, é
 * obrigatório enviar user_id + user_hash (HMAC gerado no backend). Nenhum dado
 * clínico é enviado.
 */
export function updateIntercomUser(data: {
  user_id?: string;
  user_hash?: string;
  email?: string;
  name?: string;
}): void {
  window.Intercom?.('update', data);
}
