/**
 * A espera do Data Ocean.
 *
 * Medição em produção (2026-09-08): uma consulta levou 97,9 segundos. O fluxo
 * agêntico roda inteiro do lado da Maritaca e a API não aceita streaming com a
 * ferramenta ligada — não há texto parcial para mostrar, e a demora não é do
 * nosso código.
 *
 * O que dá para mudar é a EXPECTATIVA. Uma frase estática com três pontinhos
 * por 98 segundos é indistinguível de uma tela travada. Um cronômetro correndo
 * e etapas que avançam dizem "está trabalhando" sem prometer o que não se pode
 * cumprir.
 *
 * Os testes usam timers falsos: o comportamento é temporal, e esperar 98
 * segundos de verdade num teste seria absurdo.
 */
import { render, screen, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatView } from './ChatView';

vi.mock('../hooks/useIsMobile', () => ({ useIsMobile: () => false }));

function renderEsperando(mode: string) {
  return render(
    <ChatView
      messages={[{ role: 'user', content: 'Cobertura vacinal de sarampo?' }]}
      streaming
      streamingMode={mode}
    />,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('espera do Data Ocean', () => {
  it('mostra um cronômetro — é o que separa "trabalhando" de "travado"', () => {
    renderEsperando('DATA_OCEAN');

    act(() => { vi.advanceTimersByTime(3000); });

    expect(screen.getByText(/^\d+s$/)).toBeInTheDocument();
  });

  it('avança as etapas conforme o tempo passa', () => {
    renderEsperando('DATA_OCEAN');

    expect(screen.getByText(/Escolhendo as bases/)).toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(9000); });
    expect(screen.getByText(/Consultando fontes oficiais/)).toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(9000); });
    expect(screen.getByText(/Cruzando os dados/)).toBeInTheDocument();
  });

  it('para na última etapa, sem reiniciar nem inventar progresso', () => {
    // O fluxo agêntico é interno à Maritaca: não sabemos em que passo ele está.
    // Voltar ao início daria a impressão de que travou e recomeçou.
    renderEsperando('DATA_OCEAN');

    act(() => { vi.advanceTimersByTime(120000); });

    expect(screen.getByText(/Montando a resposta com as fontes/)).toBeInTheDocument();
    expect(screen.queryByText(/Escolhendo as bases/)).not.toBeInTheDocument();
  });

  it('explica a demora depois de 25 segundos', () => {
    renderEsperando('DATA_OCEAN');

    expect(screen.queryByText(/entre 1 e 2 minutos/)).not.toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(26000); });

    expect(screen.getByText(/entre 1 e 2 minutos/)).toBeInTheDocument();
  });

  it('não muda nada nos modos rápidos', () => {
    // QUICK_SEARCH streama de verdade e responde em segundos: cronômetro e
    // aviso de demora ali seriam ruído, e pior — sugeririam lentidão onde não há.
    renderEsperando('QUICK_SEARCH');

    act(() => { vi.advanceTimersByTime(30000); });

    expect(screen.getByText(/Buscando em fontes médicas/)).toBeInTheDocument();
    expect(screen.queryByText(/^\d+s$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/entre 1 e 2 minutos/)).not.toBeInTheDocument();
  });
});
