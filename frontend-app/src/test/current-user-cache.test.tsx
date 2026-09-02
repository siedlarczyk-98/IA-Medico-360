/**
 * O cache do usuário atual precisa ser por IDENTIDADE.
 *
 * Observado em produção ao trocar de conta no LMS no mesmo navegador: a sessão
 * já era do médico novo (as conversas do anterior não apareciam, e o Editar
 * perfil mostrava a conta certa), mas a saudação e o card do rodapé exibiam o
 * NOME e o CRM de quem tinha usado antes.
 *
 * A causa era a chave fixa `['currentUser']` com `staleTime` de 5 minutos: a
 * identidade mudava e a chave não, então o react-query servia a entrada antiga.
 * Mostrar "CRM/SP 123643" para outra pessoa é grave o bastante para ter teste.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useCurrentUser } from '../lib/useCurrentUser';

const TOKEN_KEY = 'medico360_token';

/** JWT de mentira: só o payload importa, e o hook não verifica assinatura. */
function tokenPara(sub: string): string {
  const payload = btoa(JSON.stringify({ sub, role: 'beta_user', exp: 4102444800 }));
  return `cabecalho.${payload}.assinatura`;
}

function envolver(client: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('cache do usuário atual', () => {
  it('não serve o dado de um médico para outro', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = envolver(client);

    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => ({
      ok: true,
      json: async () => (
        localStorage.getItem(TOKEN_KEY) === tokenPara('medico-a')
          ? { id: 'medico-a', email: 'a@x.com', name: 'Ana Alves', crm: '111',
              crm_state: 'SP', role: 'beta_user', med_status: 'especialista',
              onboarding_complete: true }
          : { id: 'medico-b', email: 'b@x.com', name: 'Bruno Braga', crm: '222',
              crm_state: 'RJ', role: 'beta_user', med_status: 'residente',
              onboarding_complete: true }
      ),
    })));

    localStorage.setItem(TOKEN_KEY, tokenPara('medico-a'));
    const primeiro = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(primeiro.result.current?.name).toBe('Ana Alves'));
    primeiro.unmount();

    // O médico seguinte no mesmo navegador — sem limpar nada, que é o cenário
    // real da estação de plantão.
    localStorage.setItem(TOKEN_KEY, tokenPara('medico-b'));
    const segundo = renderHook(() => useCurrentUser(), { wrapper });

    await waitFor(() => expect(segundo.result.current?.name).toBe('Bruno Braga'));
    expect(segundo.result.current?.crmLabel).toBe('CRM/RJ 222');
  });

  it('não consulta a API sem token', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    renderHook(() => useCurrentUser(), { wrapper: envolver(client) });

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
