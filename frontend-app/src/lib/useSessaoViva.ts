/**
 * Mantém a sessão viva quando o app volta do segundo plano.
 *
 * A lógica mora em `shared/embed/sessao.ts`, porque as calculadoras e as
 * notícias tinham o mesmo problema e não tinham esta proteção — ver o docblock
 * de lá. Aqui só se liga o hook ao armazenamento de token deste app.
 */

import { useSessaoViva as useSessaoVivaCompartilhada } from '@shared/embed/sessao';

import { getToken, setToken } from './auth';

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export function useSessaoViva(aoExpirar?: () => void): void {
  useSessaoVivaCompartilhada({
    apiBase: API_BASE,
    getToken: () => getToken(),
    // Função, e não a referência direta: os testes espionam `auth.setToken`.
    setToken: token => setToken(token),
    aoExpirar,
  });
}
