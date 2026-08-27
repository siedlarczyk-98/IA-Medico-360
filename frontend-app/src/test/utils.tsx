/**
 * Utilitários compartilhados pelos testes de UI.
 *
 * O App real depende de auth, react-query e de quatro endpoints só para
 * montar a tela. Estes helpers isolam essa infraestrutura para que um teste
 * possa se ocupar do comportamento que quer verificar.
 */
import type { ReactElement, ReactNode } from 'react';
import { StrictMode } from 'react';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { StreamEvent } from '../api/orquestrador';

/**
 * QueryClient sem retry e sem cache entre testes. Com retry ligado, uma query
 * que falha fica reexecutando depois do fim do teste e polui o teste seguinte.
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
}

interface RenderOptions {
  /** Mantém o StrictMode, que é o que expõe updaters impuros. Ligado por padrão. */
  strict?: boolean;
  route?: string;
}

export function renderComProvedores(ui: ReactElement, options: RenderOptions = {}) {
  const { strict = true, route = '/' } = options;
  const queryClient = makeQueryClient();

  const Arvore = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );

  const conteudo = strict ? <StrictMode><Arvore>{ui}</Arvore></StrictMode> : <Arvore>{ui}</Arvore>;
  return { queryClient, ...render(conteudo) };
}

/**
 * Gerador que entrega todos os eventos SEM ceder o controle ao event loop entre
 * eles. É esta a condição que provoca a corrida de estado no streaming: vários
 * `token` processados antes de o React aplicar a primeira atualização. Um
 * gerador que dá `await` entre os eventos deixa o React respirar e NÃO
 * reproduz o bug — por isso este helper existe separado.
 */
export async function* streamEmLote(eventos: StreamEvent[]): AsyncGenerator<StreamEvent> {
  for (const evento of eventos) {
    yield evento;
  }
}

/** Monta uma sequência de tokens seguida do evento `done`. */
export function tokensEDone(
  textos: string[],
  done: Partial<Extract<StreamEvent, { type: 'done' }>> = {},
): StreamEvent[] {
  return [
    ...textos.map(text => ({ type: 'token' as const, text })),
    {
      type: 'done' as const,
      conversation_id: 'conv-1',
      mode: 'PRODUCTIVITY',
      model_used: 'gpt-5.4-nano',
      ...done,
    },
  ];
}

/** Sequência realista: tokens → `text_done` → `done`. */
export function tokensTextDoneEDone(
  textos: string[],
  done: Partial<Extract<StreamEvent, { type: 'done' }>> = {},
): StreamEvent[] {
  return [
    ...textos.map(text => ({ type: 'token' as const, text })),
    {
      type: 'text_done' as const,
      conversation_id: 'conv-1',
      mode: 'PRODUCTIVITY',
      model_used: 'gpt-5.4-nano',
      is_fallback: false,
    },
    {
      type: 'done' as const,
      conversation_id: 'conv-1',
      mode: 'PRODUCTIVITY',
      model_used: 'gpt-5.4-nano',
      ...done,
    },
  ];
}

/**
 * Stream que PARA no `text_done` e só emite o `done` quando o teste liberar.
 * Reproduz o intervalo real em que o backend está esperando o PubMed — que é
 * exatamente onde a digitação não pode estar bloqueada.
 */
export function streamComEsperaAntesDoDone(eventos: StreamEvent[]) {
  let liberar!: () => void;
  const espera = new Promise<void>(resolve => { liberar = resolve; });

  async function* gerador(): AsyncGenerator<StreamEvent> {
    for (const evento of eventos) {
      if (evento.type === 'done') await espera;
      yield evento;
    }
  }

  return { gerador, liberar };
}
