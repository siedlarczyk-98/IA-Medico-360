/**
 * O botão voltar fecha a camada de cima — e só ela — sem trocar de URL.
 */
import { waitFor } from '@testing-library/react';

import { abrirCamada, fecharCamada, fecharTodasCamadas, haCamadaAberta, reiniciarCamadas, trocarCamada, voltarPara } from './camadas';

beforeEach(() => {
  reiniciarCamadas();
  window.history.replaceState(null, '', '/');
});

describe('camadas e o botão voltar', () => {
  it('voltar fecha a de cima, depois a de baixo, e a URL não muda', async () => {
    const fechadas: string[] = [];
    abrirCamada(() => fechadas.push('gaveta'));
    abrirCamada(() => fechadas.push('folha'));
    expect(window.location.pathname).toBe('/');

    window.history.back();
    await waitFor(() => expect(fechadas).toEqual(['folha']));

    window.history.back();
    await waitFor(() => expect(fechadas).toEqual(['folha', 'gaveta']));
    expect(haCamadaAberta()).toBe(false);
    expect(window.location.pathname).toBe('/');
  });

  it('fechar pela interface passa pelo histórico, e o "depois" roda só no fim', async () => {
    const ordem: string[] = [];
    abrirCamada(() => ordem.push('fechou folha'));

    fecharCamada(() => ordem.push('depois'));
    expect(ordem).toEqual([]); // assíncrono: nada ainda

    await waitFor(() => expect(ordem).toEqual(['fechou folha', 'depois']));
  });

  it('trocar a camada de cima não mexe no histórico', async () => {
    const fechadas: string[] = [];
    abrirCamada(() => fechadas.push('ações'));
    const tamanho = window.history.length;
    trocarCamada(() => fechadas.push('mover'));
    expect(window.history.length).toBe(tamanho);

    fecharCamada();
    await waitFor(() => expect(fechadas).toEqual(['mover']));
  });

  it('fechar todas volta tudo de uma vez', async () => {
    const fechadas: string[] = [];
    abrirCamada(() => fechadas.push('gaveta'));
    abrirCamada(() => fechadas.push('pasta'));
    abrirCamada(() => fechadas.push('folha'));

    fecharTodasCamadas();
    await waitFor(() => expect(fechadas).toEqual(['folha', 'pasta', 'gaveta']));
  });

  it('preserva o state do roteador na entrada nova', () => {
    window.history.replaceState({ key: 'abc', idx: 3 }, '');
    abrirCamada(() => {});
    expect(window.history.state).toMatchObject({ key: 'abc', idx: 3, mvCamada: 1 });
  });
});

describe('voltar até um nível', () => {
  it('fecha só o que está acima e depois roda o próximo passo', async () => {
    reiniciarCamadas();
    const ordem: string[] = [];
    abrirCamada(() => ordem.push('aba'));
    abrirCamada(() => ordem.push('pasta'));
    abrirCamada(() => ordem.push('folha'));

    voltarPara(1, () => ordem.push('trocou a aba'));

    await waitFor(() => expect(ordem).toEqual(['folha', 'pasta', 'trocou a aba']));
    expect(haCamadaAberta()).toBe(true);
  });
});
