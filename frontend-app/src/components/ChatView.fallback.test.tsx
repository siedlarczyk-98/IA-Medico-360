/**
 * Uma resposta de fallback precisa parecer uma resposta de fallback.
 *
 * O caso que motivou isto é o Data Ocean. Aquele modo **não tem fallback por
 * decisão**: nenhum outro modelo consulta as bases brasileiras, e cair para o
 * Claude devolveria números plausíveis construídos da memória de treino com a
 * mesma cara de uma consulta ao DATASUS. O desenho escolheu falhar visivelmente.
 *
 * Só que a mensagem genérica de erro era gravada no histórico e reexibida
 * exatamente como uma resposta legítima — mesmo texto corrido, mesmo disclaimer,
 * sem nenhuma marca. Quem reabria a conversa lia "a resposta não ficou salva"
 * onde o correto era "a consulta falhou". O backend já emitia `is_fallback` no
 * SSE e o gravava no banco; a interface é que ignorava o campo.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChatView } from './ChatView';

vi.mock('../hooks/useIsMobile', () => ({ useIsMobile: () => false }));

const PERGUNTA = { role: 'user' as const, content: 'Cobertura vacinal de sarampo?' };
const ERRO = 'Desculpe, não foi possível processar sua consulta no momento.';

function renderResposta(is_fallback?: boolean, content = ERRO) {
  return render(
    <ChatView
      messages={[
        PERGUNTA,
        { role: 'assistant', content, mode: 'dados', is_fallback },
      ]}
    />,
  );
}

const aviso = () => screen.queryByText(/não vem das bases consultadas/i);

describe('Aviso de resposta que não veio do modo escolhido', () => {
  it('aparece quando a resposta é fallback', () => {
    renderResposta(true);
    expect(aviso()).toBeInTheDocument();
  });

  it('NÃO aparece numa resposta normal', () => {
    // O ponto: o aviso precisa ser raro para significar alguma coisa.
    renderResposta(false, 'Em 2025 a cobertura foi de 87%.');
    expect(aviso()).toBeNull();
  });

  it('não aparece quando o campo nem vem (conversa antiga)', () => {
    // Respostas gravadas antes de `is_fallback` chegar à API vêm sem o campo.
    // Ausência é tratada como "não é fallback": marcar tudo o que não se sabe
    // encheria o histórico de avisos e destruiria o significado deles.
    renderResposta(undefined, 'Resposta de antes da mudança.');
    expect(aviso()).toBeNull();
  });

  it('vem ANTES do texto da resposta, não depois', () => {
    // O aviso existe para mudar como o médico LÊ o que está abaixo. Um rodapé
    // chegaria depois de ele já ter lido.
    const { container } = renderResposta(true);

    const texto = container.textContent ?? '';
    expect(texto.indexOf('não vem das bases consultadas')).toBeLessThan(
      texto.indexOf('não foi possível processar'),
    );
  });

  it('o texto da resposta continua visível', () => {
    // Marcar não é esconder: o médico precisa ver o que o sistema respondeu.
    renderResposta(true);
    expect(screen.getByText(new RegExp(ERRO.slice(0, 30), 'i'))).toBeInTheDocument();
  });

  it('é anunciado como nota para leitor de tela', () => {
    renderResposta(true);
    expect(screen.getByRole('note')).toBeInTheDocument();
  });
});
