/**
 * Mantém a sessão viva quando o app volta do segundo plano.
 *
 * O PROBLEMA, medido no aplicativo
 * O JWT vale 60 min e não havia renovação: passou disso, o próximo pedido leva
 * 401 e o médico cai no login. No navegador isso quase não aparece, porque a
 * aba fica viva e ele recarrega sem pensar. No aplicativo é o caso comum —
 * minimizar, atender um paciente, voltar. O sintoma relatado é "o app me
 * desloga sozinho".
 *
 * Há DUAS causas distintas por trás do mesmo sintoma, e só uma tem conserto
 * aqui:
 *
 *  1. **o token venceu enquanto o app estava parado** — é o que este hook
 *     resolve, renovando ao voltar e antes de vencer;
 *  2. **o webview foi recolhido da memória e o `localStorage` voltou vazio** —
 *     nada em JavaScript recupera um token que não existe mais. Aí o login é
 *     inevitável; o que dá para fazer é não somar a causa (1) a ela.
 *
 * POR QUE NÃO UM TIMER SOZINHO
 * Um `setInterval` não roda de forma confiável com o app em segundo plano: o
 * sistema congela o webview e o timer que deveria disparar aos 50 min dispara
 * quando o app volta — tarde demais. Por isso o gatilho principal é a VOLTA
 * (`visibilitychange`), com o timer como reforço para quem fica horas com a
 * tela aberta.
 */

import { useEffect } from 'react';

import { getToken, getTokenPayload, setToken } from './auth';

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

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

function precisaRenovar(): boolean {
  const payload = getTokenPayload();
  if (!payload) return false; // sem token não há o que renovar: é caso de login
  return payload.exp * 1000 - Date.now() < MARGEM_MS;
}

/**
 * Troca o token por um novo. Silenciosa por contrato.
 *
 * Falhar aqui NÃO pode derrubar ninguém: se a renovação não vai, o token atual
 * continua valendo até vencer, e aí o 401 normal cuida do assunto. Deslogar por
 * causa de uma renovação que falhou seria criar o problema que viemos evitar.
 */
async function renovar(): Promise<void> {
  const token = getToken();
  if (!token) return;
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/session/renew`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(10_000),
    });
    // 401 aqui significa sessão de 24h encerrada ou logout em outro aparelho.
    // Não limpamos nada: o `RequireAuth` e o 401 da próxima chamada já levam
    // ao login pelo caminho normal, com a mensagem certa.
    if (!resp.ok) return;
    const dados = (await resp.json()) as { access_token?: string };
    if (dados.access_token) setToken(dados.access_token);
  } catch {
    /* rede ruim ou app voltando: o token atual segue valendo */
  }
}

export function useSessaoViva(): void {
  useEffect(() => {
    function aoVoltar() {
      // `document.hidden` cobre os dois lados do evento; só agimos na volta.
      if (document.hidden) return;
      if (precisaRenovar()) void renovar();
    }

    // Renova já na montagem se o app abriu com um token quase vencido —
    // acontece quando o webview foi restaurado depois de muito tempo parado.
    if (precisaRenovar()) void renovar();

    document.addEventListener('visibilitychange', aoVoltar);
    // `pageshow` cobre o bfcache: em iOS o app volta da memória sem disparar
    // `visibilitychange`, e a página revive exatamente como estava.
    window.addEventListener('pageshow', aoVoltar);
    const timer = setInterval(aoVoltar, INTERVALO_MS);

    return () => {
      document.removeEventListener('visibilitychange', aoVoltar);
      window.removeEventListener('pageshow', aoVoltar);
      clearInterval(timer);
    };
  }, []);
}
