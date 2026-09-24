/**
 * Sessão que sobrevive ao celular — o mesmo código nos três apps.
 *
 * O PROBLEMA, medido no aplicativo
 * O JWT vale 60 min. No navegador isso quase não aparece, porque a aba fica
 * viva e o médico recarrega sem pensar. No aplicativo da Waid é o caso comum —
 * minimizar, atender um paciente, voltar. Nas calculadoras o sintoma era
 * "Calculadora não encontrada" ao alternar entre a lista e uma calculadora
 * (o 401 caía no mesmo ramo do 404); nas notícias, "Token expirado" cru no
 * modal do destaque. Só o chat renovava, e só ele tinha este código.
 *
 * Há DUAS situações distintas por trás do mesmo sintoma:
 *
 *  1. **o token está perto de vencer** — `useSessaoViva` troca por outro em
 *     `/auth/session/renew`. Só funciona com token AINDA válido: o backend não
 *     ressuscita sessão morta;
 *  2. **o token já venceu** (o app ficou mais de uma hora em segundo plano, com
 *     os timers congelados) — renovar não serve mais. Dentro da Waid a saída é
 *     pedir a identidade de novo pelo handshake, que é silencioso; fora dela,
 *     o login. É o `aoExpirar` e o `reservarReentradaPelaWaid`.
 *
 * Nada em JavaScript cobre o terceiro caso: o webview recolhido da memória que
 * volta com o `localStorage` vazio. Ali a entrada é refeita do zero.
 */

import { useEffect, useRef } from 'react';

import { temIframe, temPonteNativa } from './identidade';

/**
 * Renova quando falta menos que isto para vencer.
 *
 * Dez minutos de folga contra um token de 60: largo o bastante para cobrir
 * relógio dessincronizado entre aparelho e servidor (o `exp` é do servidor, o
 * `Date.now()` é do aparelho) e uma rede ruim na hora de renovar.
 */
const MARGEM_MS = 10 * 60 * 1000;

/** Reforço para a aba que fica aberta sem nunca ser escondida. */
const INTERVALO_MS = 5 * 60 * 1000;

/**
 * Janela em que uma segunda reentrada pela Waid NÃO é tentada.
 *
 * Se o token que acabou de chegar pelo handshake também leva 401 (conta
 * desativada, relógio do servidor torto), mandar de volta ao handshake giraria
 * para sempre. Um minuto é mais do que um handshake leva e menos do que alguém
 * espera entre duas quedas legítimas.
 */
const JANELA_REENTRADA_MS = 60 * 1000;
const CHAVE_REENTRADA = 'm360_reentrada_waid_em';

/** `exp` do JWT, em milissegundos. `null` quando não dá para ler. */
export function expiracaoDoToken(token: string | null): number | null {
  if (!token) return null;
  try {
    const parte = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const exp = (JSON.parse(atob(parte)) as { exp?: unknown }).exp;
    return typeof exp === 'number' ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/**
 * Estamos dentro da Waid — app nativo (ponte) ou site (iframe)?
 *
 * É a pergunta que decide para onde vai quem perdeu a sessão: ali existe um
 * canal para pedir a identidade de novo sem incomodar o médico.
 */
export function hospedadoNaWaid(): boolean {
  return temIframe() || temPonteNativa();
}

/**
 * Pode tentar entrar de novo pela Waid? Se sim, já marca a tentativa.
 *
 * Devolve `false` fora da Waid (não há handshake possível) e quando houve uma
 * reentrada há menos de `JANELA_REENTRADA_MS` — a trava contra laço. Quem
 * recebe `false` deve cair no login por e-mail, que é porta legítima.
 *
 * Tem efeito colateral de propósito (grava a marca): chamar só em handler ou
 * efeito, nunca no corpo de um render — o StrictMode renderiza duas vezes e a
 * segunda chamada acharia a marca da primeira.
 */
export function reservarReentradaPelaWaid(): boolean {
  if (!hospedadoNaWaid()) return false;
  try {
    const ultima = Number(sessionStorage.getItem(CHAVE_REENTRADA) ?? 0);
    if (Date.now() - ultima < JANELA_REENTRADA_MS) return false;
    sessionStorage.setItem(CHAVE_REENTRADA, String(Date.now()));
  } catch {
    // Sem sessionStorage não há como travar o laço; melhor o login do que girar.
    return false;
  }
  return true;
}

interface OpcoesSessaoViva {
  apiBase: string;
  getToken: () => string | null;
  setToken: (token: string) => void;
  /**
   * O app voltou do segundo plano com o token JÁ vencido. Cada app decide como
   * entrar de novo (rota de embed, recarregar a página). Sem isto, o médico só
   * descobre na próxima ação — e nas calculadoras a descoberta era uma tela de
   * "não encontrada".
   */
  aoExpirar?: () => void;
}

/**
 * Troca o token por um novo. Silenciosa por contrato.
 *
 * Falhar aqui NÃO pode derrubar ninguém: se a renovação não vai, o token atual
 * continua valendo até vencer, e aí o 401 normal cuida do assunto. Deslogar por
 * causa de uma renovação que falhou seria criar o problema que viemos evitar.
 */
async function renovar({ apiBase, getToken, setToken }: OpcoesSessaoViva): Promise<void> {
  const token = getToken();
  if (!token) return;
  try {
    const resp = await fetch(`${apiBase}/api/v1/auth/session/renew`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(10_000),
    });
    // 401 aqui significa sessão de 24h encerrada ou logout em outro aparelho.
    // Não limpamos nada: o 401 da próxima chamada leva à reentrada pelo
    // caminho normal, com a mensagem certa.
    if (!resp.ok) return;
    const dados = (await resp.json()) as { access_token?: string };
    if (dados.access_token) setToken(dados.access_token);
  } catch {
    /* rede ruim ou app voltando: o token atual segue valendo */
  }
}

/**
 * Mantém a sessão viva.
 *
 * POR QUE NÃO UM TIMER SOZINHO
 * Um `setInterval` não roda de forma confiável com o app em segundo plano: o
 * sistema congela o webview e o timer que deveria disparar aos 50 min dispara
 * quando o app volta — tarde demais. Por isso o gatilho principal é a VOLTA
 * (`visibilitychange`/`pageshow`), com o timer como reforço. O timer não exige
 * a tela visível: no computador a aba escondida continua rodando timers (mais
 * devagar), e renovar ali evita que a aba de fundo expire à toa.
 */
export function useSessaoViva(opcoes: OpcoesSessaoViva): void {
  // Ref para as opções: callbacks novos a cada render não podem recriar os
  // ouvintes (e o timer) toda hora.
  const ref = useRef(opcoes);
  ref.current = opcoes;

  useEffect(() => {
    function verificar({ naVolta }: { naVolta: boolean }) {
      const o = ref.current;
      const exp = expiracaoDoToken(o.getToken());
      if (exp === null) return; // sem token não há o que renovar: é caso de login
      const falta = exp - Date.now();
      if (falta <= 0) {
        // Só na VOLTA: é quando o médico vai tocar na tela. No timer, a aba de
        // fundo que venceu espera ele voltar — tirá-lo da tela que ele deixou
        // aberta, sem ele estar olhando, não ajuda ninguém.
        if (naVolta) o.aoExpirar?.();
        return;
      }
      if (falta < MARGEM_MS) void renovar(o);
    }

    function aoVoltar() {
      // `document.hidden` cobre os dois lados do evento; só agimos na volta.
      if (document.hidden) return;
      verificar({ naVolta: true });
    }

    // Renova já na montagem se o app abriu com um token quase vencido —
    // acontece quando o webview foi restaurado depois de muito tempo parado.
    // Token JÁ vencido na montagem é assunto da rota (`RequireAuth`, handshake).
    verificar({ naVolta: false });

    document.addEventListener('visibilitychange', aoVoltar);
    // `pageshow` cobre o bfcache: em iOS o app volta da memória sem disparar
    // `visibilitychange`, e a página revive exatamente como estava.
    window.addEventListener('pageshow', aoVoltar);
    const timer = setInterval(() => verificar({ naVolta: false }), INTERVALO_MS);

    return () => {
      document.removeEventListener('visibilitychange', aoVoltar);
      window.removeEventListener('pageshow', aoVoltar);
      clearInterval(timer);
    };
  }, []);
}
