/**
 * O LEITOR SSE de verdade, e o contrato com o backend.
 *
 * `streamQuery` tinha 2,4% de cobertura: todo teste do chat o substitui por mock.
 * O que ele faz de difícil — remontar eventos a partir de pedaços de rede que
 * cortam em qualquer lugar, inclusive no meio de um caractere acentuado — nunca
 * tinha sido exercitado. Aqui o `fetch` devolve um corpo de verdade, fatiado.
 */
import { CONTRATO_SSE } from '@shared/contrato-sse';
// `?raw`: o Vite entrega o arquivo como texto. Evita depender de `node:fs` (o chat
// não tem `@types/node`, e instalar dependência aqui regenera o lockfile).
// É o controller, e não o App: o tratamento dos eventos saiu do App quando a
// lógica do chat foi separada da casca (desktop/mobile).
import fonteDoChat from '../chat/useChatController.ts?raw';
import { type StreamEvent, streamQuery } from './orquestrador';
import { ErroDeApi } from './erros';

vi.mock('../lib/auth', () => ({ getToken: () => 'token-de-teste' }));

const CONTRATO: Record<string, 'tratado' | 'informativo'> = CONTRATO_SSE;

function frame(evento: string, dados: object): string {
  return `event: ${evento}\ndata: ${JSON.stringify(dados)}\n\n`;
}

const CORPO =
  frame('start', { mode: 'QUICK_SEARCH', triage_confidence: 0.99 }) +
  frame('token', { text: 'Posologia: ' }) +
  ': ping\n\n' +
  frame('token', { text: 'amoxicilina 500 mg — 8/8h, atenção à função renal.' }) +
  frame('text_done', { conversation_id: 'conv-1', mode: 'QUICK_SEARCH' }) +
  frame('done', { conversation_id: 'conv-1', mode: 'QUICK_SEARCH', is_fallback: false });

const ESPERADO = [
  { type: 'start', mode: 'QUICK_SEARCH', triage_confidence: 0.99 },
  { type: 'token', text: 'Posologia: ' },
  { type: 'token', text: 'amoxicilina 500 mg — 8/8h, atenção à função renal.' },
  { type: 'text_done', conversation_id: 'conv-1', mode: 'QUICK_SEARCH' },
  { type: 'done', conversation_id: 'conv-1', mode: 'QUICK_SEARCH', is_fallback: false },
];

/** Resposta cujo corpo chega nos pedaços dados — cortes em BYTES, como na rede. */
function respostaEmPedacos(bytes: Uint8Array, cortes: number[]): Response {
  const limites = [0, ...cortes, bytes.length];
  const corpo = new ReadableStream<Uint8Array>({
    start(controle) {
      for (let i = 0; i < limites.length - 1; i++) {
        if (limites[i + 1] > limites[i]) controle.enqueue(bytes.slice(limites[i], limites[i + 1]));
      }
      controle.close();
    },
  });
  return new Response(corpo, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

async function ler(resposta: Response): Promise<StreamEvent[]> {
  vi.stubGlobal('fetch', vi.fn(async () => resposta));
  const eventos: StreamEvent[] = [];
  for await (const evento of streamQuery({ prompt: 'dose de amoxicilina?' })) eventos.push(evento);
  return eventos;
}

afterEach(() => vi.unstubAllGlobals());

describe('leitor SSE', () => {
  const bytes = new TextEncoder().encode(CORPO);

  it('remonta os eventos com o corpo chegando inteiro', async () => {
    expect(await ler(respostaEmPedacos(bytes, []))).toEqual(ESPERADO);
  });

  it('dá o MESMO resultado com o corte em qualquer byte do corpo', async () => {
    // Todas as posições, uma a uma: no meio de "event:", no meio do JSON, entre os
    // dois \n do fim do frame, e no meio dos caracteres de 2 e 3 bytes ("ç", "—").
    for (let corte = 1; corte < bytes.length; corte++) {
      const eventos = await ler(respostaEmPedacos(bytes, [corte]));
      expect(eventos, `corte no byte ${corte}`).toEqual(ESPERADO);
    }
  });

  it('e com o corpo chegando byte a byte', async () => {
    const todos = Array.from({ length: bytes.length - 1 }, (_, i) => i + 1);

    expect(await ler(respostaEmPedacos(bytes, todos))).toEqual(ESPERADO);
  });

  it('o heartbeat `: ping` não vira evento', async () => {
    const eventos = await ler(respostaEmPedacos(bytes, []));

    expect(eventos).toHaveLength(ESPERADO.length);
    expect(JSON.stringify(eventos)).not.toContain('ping');
  });

  it('linha de dados malformada é ignorada, e o stream segue', async () => {
    const corpo = frame('token', { text: 'antes' }) + 'event: token\ndata: {quebrado\n\n' + frame('token', { text: 'depois' });

    const eventos = await ler(respostaEmPedacos(new TextEncoder().encode(corpo), []));

    expect(eventos).toEqual([{ type: 'token', text: 'antes' }, { type: 'token', text: 'depois' }]);
  });

  it('resposta de erro HTTP vira ErroDeApi com o status, antes de ler qualquer corpo', async () => {
    const limite = new Response(JSON.stringify({ detail: 'Limite semanal de uso atingido.' }), { status: 429 });

    await expect(ler(limite)).rejects.toMatchObject({ status: 429, message: 'Limite semanal de uso atingido.' });
    await expect(ler(new Response('{}', { status: 401 }))).rejects.toBeInstanceOf(ErroDeApi);
  });
});

describe('contrato SSE com o backend', () => {
  // `shared/contrato-sse.ts` é conferido nas duas pontas. O lado do backend
  // (`tests/test_contrato_sse.py`) garante que ele só emite o que está lá.
  const tratados = new Set([...fonteDoChat.matchAll(/event\.type === '([a-z_]+)'/g)].map(m => m[1]));

  it('o chat trata todo evento marcado como "tratado"', () => {
    const faltando = Object.entries(CONTRATO)
      .filter(([, papel]) => papel === 'tratado')
      .map(([nome]) => nome)
      .filter(nome => !tratados.has(nome));

    expect(faltando, 'evento do backend sem tratamento no chat — a informação some em silêncio').toEqual([]);
  });

  it('o chat não espera por evento que o backend nunca manda', () => {
    const fantasmas = [...tratados].filter(nome => !(nome in CONTRATO));

    expect(fantasmas).toEqual([]);
  });

  it('a varredura enxerga o tratamento (senão os testes acima passariam vazios)', () => {
    expect(tratados.size).toBeGreaterThanOrEqual(5);
  });
});
