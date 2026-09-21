/**
 * Rolagem do chat (item 35 da varredura de 2026-09-18).
 *
 * Rolava-se até o fim UMA vez, no envio: a resposta crescia para fora da tela e o
 * médico rolava à mão por até um minuto, a cada pergunta. E ao trocar de
 * conversa a rolagem da anterior ficava.
 */
import { render, screen } from '@testing-library/react';
import { ChatView } from './ChatView';
import type { Message } from '../api/orquestrador';

const CONVERSA: Message[] = [
  { role: 'user', content: 'pergunta antiga' },
  { role: 'assistant', content: 'resposta antiga' },
  { role: 'user', content: 'pergunta nova' },
  { role: 'assistant', content: 'resposta nova chegando' },
];

const scrollIntoView = vi.mocked(window.HTMLElement.prototype.scrollIntoView);

beforeEach(() => scrollIntoView.mockClear());

describe('ChatView — rolagem', () => {
  it('ao enviar, leva a PERGUNTA ao topo, em vez de rolar até o fim', () => {
    const { rerender } = render(<ChatView messages={CONVERSA} scrollToBottomTrigger={0} />);
    expect(scrollIntoView).not.toHaveBeenCalled();

    rerender(<ChatView messages={CONVERSA} scrollToBottomTrigger={1} />);

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    // Quem rolou foi o último turno, que começa na última pergunta do usuário.
    const turno = screen.getByTestId('ultimo-turno');
    expect(scrollIntoView.mock.contexts[0]).toBe(turno);
    expect(turno).toHaveTextContent('pergunta nova');
    expect(turno).toHaveTextContent('resposta nova chegando');
    expect(turno).not.toHaveTextContent('pergunta antiga');
  });

  it('o turno ganha a altura da área visível, para a resposta ter onde crescer', () => {
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 640 });
    try {
      const { rerender } = render(<ChatView messages={CONVERSA} scrollToBottomTrigger={0} />);
      rerender(<ChatView messages={CONVERSA} scrollToBottomTrigger={1} />);

      expect(screen.getByTestId('ultimo-turno')).toHaveStyle({ minHeight: '640px' });
    } finally {
      delete (HTMLElement.prototype as { clientHeight?: number }).clientHeight;
    }
  });

  it('abrir outra conversa vai direto ao fim e desfaz a âncora', () => {
    const { rerender } = render(<ChatView messages={CONVERSA} scrollToBottomTrigger={1} conversationOpenedTrigger={0} />);
    scrollIntoView.mockClear();

    rerender(<ChatView messages={CONVERSA} scrollToBottomTrigger={1} conversationOpenedTrigger={1} />);

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'auto', block: 'end' });
    // Sem isto sobraria um vão em branco do tamanho da tela no fim da conversa.
    expect(screen.getByTestId('ultimo-turno').style.minHeight).toBe('');
  });

  it('tokens chegando não disparam rolagem: quem rola, a partir daí, é o médico', () => {
    const { rerender } = render(<ChatView messages={CONVERSA} scrollToBottomTrigger={1} />);
    scrollIntoView.mockClear();

    const crescendo = [...CONVERSA.slice(0, 3), { role: 'assistant' as const, content: 'resposta nova chegando, com mais texto' }];
    rerender(<ChatView messages={crescendo} scrollToBottomTrigger={1} streaming />);

    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('mensagens antigas não são remontadas quando o turno muda', () => {
    const { rerender } = render(<ChatView messages={CONVERSA.slice(0, 2)} />);
    const antiga = screen.getByText('resposta antiga');

    rerender(<ChatView messages={CONVERSA} />);

    expect(screen.getByText('resposta antiga')).toBe(antiga);
  });
});
