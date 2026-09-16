/**
 * A seção "Referências verificadas no PubMed".
 *
 * POR QUE ESTE ARQUIVO EXISTE
 * ---------------------------
 * Este componente nunca foi exercitado — nem por teste, nem em produção. A
 * validação PubMed do backend estava quebrada desde o primeiro commit do
 * `pubmed_service.py` (`max_tokens` numa família gpt-5 → HTTP 400 → engolido por
 * um `except` amplo), então `pubmed_validation` chegava sempre vazio e a seção
 * simplesmente não renderizava.
 *
 * Corrigido em 2026-09-16. Ou seja: **é código que estava morto na prática e vai
 * passar a aparecer na tela pela primeira vez.** Estrear sem teste, numa área
 * que exibe procedência de afirmação clínica, é o pior momento para descobrir um
 * defeito de renderização.
 *
 * O que se afirma aqui é a honestidade da exibição: uma citação verificada tem
 * PMID e vira link para o PubMed; uma NÃO verificada aparece como texto simples,
 * sem link — porque um link sugere confirmação que não houve.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ChatView } from './ChatView';

vi.mock('../hooks/useIsMobile', () => ({ useIsMobile: () => false }));

type Validation = {
  cited_verified: Array<{ title: string; pmid: string | null; verified: boolean }>;
  newer_guidelines: Array<{ pmid: string; article_title: string; abstract_snippet: string }>;
};

function renderComPubmed(validation: Validation) {
  return render(
    <ChatView
      messages={[
        { role: 'user', content: 'Qual a conduta na IC com FE reduzida?' },
        {
          role: 'assistant',
          content: 'Segundo as diretrizes[1], recomenda-se...',
          mode: 'busca',
          pubmed_validation: validation,
        },
      ]}
    />,
  );
}

const VAZIO: Validation = { cited_verified: [], newer_guidelines: [] };

describe('Citações verificadas', () => {
  it('citação com PMID vira link para o PubMed', () => {
    renderComPubmed({
      ...VAZIO,
      cited_verified: [
        { title: '2026 ESC Guidelines for heart failure', pmid: '42661420', verified: true },
      ],
    });

    const link = screen.getByRole('link', { name: /2026 ESC Guidelines/ });
    expect(link).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/42661420/');
  });

  it('citação SEM PMID aparece como texto, nunca como link', () => {
    // A invariante central: o modelo citou algo que a busca no PubMed não
    // confirmou. Virar link sugeriria uma verificação que não aconteceu — e o
    // médico clicaria esperando o artigo.
    renderComPubmed({
      ...VAZIO,
      cited_verified: [
        { title: 'Diretriz que o modelo citou mas não existe', pmid: null, verified: false },
      ],
    });

    expect(screen.getByText(/Diretriz que o modelo citou/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Diretriz que o modelo citou/ })).toBeNull();
  });

  it('verificadas e não verificadas convivem na mesma lista', () => {
    renderComPubmed({
      ...VAZIO,
      cited_verified: [
        { title: 'Existe de verdade', pmid: '111', verified: true },
        { title: 'Não confirmada', pmid: null, verified: false },
      ],
    });

    expect(screen.getByRole('link', { name: 'Existe de verdade' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Não confirmada' })).toBeNull();
  });

  it('link abre em aba nova, com rel seguro', () => {
    // `noopener` não é detalhe: sem ele a página de destino ganha acesso a
    // `window.opener`.
    renderComPubmed({
      ...VAZIO,
      cited_verified: [{ title: 'Artigo', pmid: '222', verified: true }],
    });

    const link = screen.getByRole('link', { name: 'Artigo' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
  });

  it('sem citações, o cabeçalho não aparece', () => {
    // Cabeçalho sobre lista vazia parece erro de carregamento.
    renderComPubmed({ ...VAZIO, newer_guidelines: [
      { pmid: '1', article_title: 'Uma diretriz', abstract_snippet: '' },
    ] });

    expect(screen.queryByText(/Referências verificadas no PubMed/i)).toBeNull();
  });
});

describe('Diretrizes recentes', () => {
  it('começa recolhida, mostrando a contagem', () => {
    // São diretrizes que o modelo NÃO citou. Abertas por padrão, competiriam
    // com a resposta; a contagem é o que convida a abrir.
    renderComPubmed({
      ...VAZIO,
      newer_guidelines: [
        { pmid: '1', article_title: 'Diretriz nova A', abstract_snippet: 'resumo' },
        { pmid: '2', article_title: 'Diretriz nova B', abstract_snippet: 'resumo' },
      ],
    });

    expect(screen.getByText(/Diretrizes recentes relacionadas \(2\)/)).toBeInTheDocument();
    expect(screen.queryByText('Diretriz nova A')).toBeNull();
  });

  it('clicar expande e mostra os artigos', async () => {
    const user = userEvent.setup();
    renderComPubmed({
      ...VAZIO,
      newer_guidelines: [
        { pmid: '42661426', article_title: 'Diretriz nova A', abstract_snippet: 'resumo' },
      ],
    });

    await user.click(screen.getByText(/Diretrizes recentes relacionadas/));

    const link = screen.getByRole('link', { name: /Diretriz nova A/ });
    expect(link).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/42661426/');
  });

  it('sem diretrizes novas, não há o que expandir', () => {
    renderComPubmed({
      ...VAZIO,
      cited_verified: [{ title: 'Artigo', pmid: '1', verified: true }],
    });

    expect(screen.queryByText(/Diretrizes recentes relacionadas/)).toBeNull();
  });
});

describe('Ausência da validação', () => {
  it('resposta sem pubmed_validation não mostra a seção', () => {
    // O caso de toda conversa gravada antes da correção — e dos modos que não
    // validam (só QUICK_SEARCH e CLINICAL_REASONING o fazem, por design).
    render(
      <ChatView
        messages={[
          { role: 'user', content: 'pergunta' },
          { role: 'assistant', content: 'resposta', mode: 'busca' },
        ]}
      />,
    );

    expect(screen.queryByText(/Referências verificadas no PubMed/i)).toBeNull();
    expect(screen.queryByText(/Diretrizes recentes/i)).toBeNull();
  });

  it('validação com as duas listas vazias não deixa bloco órfão', () => {
    // É o que o backend devolve quando a validação roda e não acha nada — e era
    // também o resultado do fallback, durante todo o tempo em que o serviço
    // esteve quebrado.
    renderComPubmed(VAZIO);

    expect(screen.queryByText(/Referências verificadas no PubMed/i)).toBeNull();
    expect(screen.queryByText(/Diretrizes recentes/i)).toBeNull();
  });
});
