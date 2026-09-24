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
 * `AbortSignal.timeout` com saída para quem não o tem.
 *
 * Webview Android abaixo da versão 103 não tem `AbortSignal.timeout`: a chamada
 * lança `TypeError` ANTES do `fetch`, o `catch` engole, e a renovação nunca
 * acontece — o médico cai na expiração de 60 min toda vez, sem erro nenhum.
 */
function sinalComTeto(ms: number): AbortSignal {
  if (typeof AbortSignal.timeout === 'function') return AbortSignal.timeout(ms);
  const controle = new AbortController();
  setTimeout(() => controle.abort(), ms);
  return controle.signal;
}

type ResultadoRenovacao = 'renovado' | 'recusado' | 'falhou';

/**
 * Troca o token por um novo.
 *
 * Falha de REDE aqui não pode derrubar ninguém: se a renovação não vai, o token
 * atual continua valendo até vencer. Deslogar por causa de um wi-fi ruim seria
 * criar o problema que viemos evitar.
 *
 * 401 é outra coisa: o servidor está dizendo que este token já não vale — sessão
 * de 24 h encerrada, ou "Sair" em outro aparelho (o logout revoga TODOS). A
 * primeira versão ignorava o 401 também, contando que "a próxima chamada leva à
 * reentrada". No chat essa próxima chamada não levava a lugar nenhum, e o médico
 * ficava com "sessão expirada" na tela e nenhuma saída. Ver `useSessaoViva`.
 */
async function renovar({ apiBase, getToken, setToken }: OpcoesSessaoViva): Promise<ResultadoRenovacao> {
  const token = getToken();
  if (!token) return 'falhou';
  try {
    const resp = await fetch(`${apiBase}/api/v1/auth/session/renew`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${token}` },
      signal: sinalComTeto(10_000),
    });
    if (resp.status === 401) return 'recusado';
    if (!resp.ok) return 'falhou';
    const dados = (await resp.json()) as { access_token?: string };
    if (!dados.access_token) return 'falhou';
    setToken(dados.access_token);
    return 'renovado';
  } catch {
    /* rede ruim ou app voltando: o token atual segue valendo */
    return 'falhou';
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
    // O servidor recusou este token numa renovação feita pelo timer, com o
    // médico longe da tela. Guardado para a próxima volta, pela mesma regra do
    // token vencido: não se tira ninguém da tela sem ele estar olhando.
    let recusadoPor: string | null = null;

    function verificar({ naVolta }: { naVolta: boolean }) {
      const o = ref.current;
      const token = o.getToken();
      const exp = expiracaoDoToken(token);
      if (exp === null) return; // sem token não há o que renovar: é caso de login
      if (naVolta && recusadoPor !== null && recusadoPor === token) {
        recusadoPor = null;
        o.aoExpirar?.();
        return;
      }
      const falta = exp - Date.now();
      if (falta <= 0) {
        // Só na VOLTA: é quando o médico vai tocar na tela. No timer, a aba de
        // fundo que venceu espera ele voltar — tirá-lo da tela que ele deixou
        // aberta, sem ele estar olhando, não ajuda ninguém.
        if (naVolta) o.aoExpirar?.();
        return;
      }
      if (falta < MARGEM_MS) {
        void renovar(o).then(resultado => {
          if (resultado !== 'recusado') return;
          // Token trocado no meio (outra aba, reentrada): a recusa era do antigo.
          if (ref.current.getToken() !== token) return;
          if (naVolta) ref.current.aoExpirar?.();
          else recusadoPor = token;
        });
      }
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
