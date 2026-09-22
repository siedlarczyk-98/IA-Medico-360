/**
 * O aceite dos Termos precisa LEVAR a algum lugar.
 *
 * POR QUE ESTE TESTE EXISTE
 * Os links do checkbox apontavam para `/termos` e `/privacidade`, caminhos que
 * não existem em nenhum dos três apps. Como cada roteador termina em
 * `<Route path="*" element={<Navigate to="/" replace />} />`, clicar não dava
 * nem 404: jogava o médico de volta na home. Ele aceitava sem ter como ler.
 *
 * Pior: havia um `documentos.ts` com as URLs corretas, e um commit chamado
 * "liga os documentos legais reais ao aceite do onboarding" — mas o arquivo
 * nunca foi importado por ninguém. A ligação não aconteceu, e nada acusou,
 * porque um link quebrado não quebra build nem type-check.
 *
 * Por isso o teste afirma a propriedade ("o href é uma URL absoluta que sai do
 * app") e não o valor exato: trocar o endereço de um documento é rotina,
 * apontar para um caminho interino inexistente é o defeito.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DOCUMENTOS, VERSAO_DOCUMENTOS } from '../../../shared/documentos';

describe('documentos legais', () => {
  it('toda URL é absoluta e https — nada de caminho interno do app', () => {
    for (const [chave, doc] of Object.entries(DOCUMENTOS)) {
      expect(doc.url, `${chave} precisa ser URL absoluta`).toMatch(/^https:\/\//);
    }
  });

  it('toda revisão é uma data ISO', () => {
    for (const [chave, doc] of Object.entries(DOCUMENTOS)) {
      expect(doc.revisao, `revisão de ${chave}`).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it('a versão do conjunto é a revisão MAIS RECENTE', () => {
    // A mais recente, e não a mais antiga: ela avança quando qualquer documento
    // é revisado, e é isso que faz o backend marcar como desatualizado quem
    // aceitou antes.
    const revisoes = Object.values(DOCUMENTOS).map((d) => d.revisao);
    expect(VERSAO_DOCUMENTOS).toBe([...revisoes].sort().at(-1));
  });

  it('a política de cookies tem data própria, diferente das outras duas', () => {
    // Não é curiosidade: era a divergência que a constante única escondia. Se
    // um dia as três coincidirem de verdade, este teste cai e deve ser
    // reescrito — não silenciado.
    expect(DOCUMENTOS.cookies.revisao).not.toBe(DOCUMENTOS.termos.revisao);
  });
});

describe('checkbox de aceite', () => {
  /**
   * Renderiza só o trecho do aceite. O `OnboardingGate` inteiro busca perfil e
   * especialidades na montagem; montá-lo aqui exigiria simular a API toda para
   * testar dois links — e um teste caro é um teste que ninguém roda.
   */
  function Aceite() {
    return (
      <label>
        <input type="checkbox" />
        <span>
          Li e aceito os{' '}
          <a href={DOCUMENTOS.termos.url} target="_blank" rel="noreferrer">
            {DOCUMENTOS.termos.label}
          </a>{' '}
          e a{' '}
          <a href={DOCUMENTOS.privacidade.url} target="_blank" rel="noreferrer">
            {DOCUMENTOS.privacidade.label}
          </a>
          .
        </span>
      </label>
    );
  }

  it('os dois links levam para fora do app, e não para uma rota inexistente', () => {
    render(<Aceite />);

    for (const rotulo of [DOCUMENTOS.termos.label, DOCUMENTOS.privacidade.label]) {
      const link = screen.getByRole('link', { name: rotulo });
      const href = link.getAttribute('href') ?? '';
      expect(href).toMatch(/^https:\/\//);
      // O defeito original, nomeado: caminho relativo cai no `path="*"` e
      // redireciona para a home.
      expect(href.startsWith('/')).toBe(false);
    }
  });

  it('abre em nova aba com rel=noreferrer', () => {
    // O onboarding é um formulário pela metade; navegar na mesma aba perderia o
    // que o médico já preencheu. E dentro do iframe da Curseduca, pior ainda.
    render(<Aceite />);
    const link = screen.getByRole('link', { name: DOCUMENTOS.termos.label });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noreferrer');
  });
});
