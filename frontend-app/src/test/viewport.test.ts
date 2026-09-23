/**
 * O `matchMedia` falso precisa acertar as consultas, senão todo teste de
 * layout mobile passa ou falha pelo motivo errado.
 */
import { avaliarConsulta, definirViewport, VIEWPORT_CELULAR, VIEWPORT_CELULAR_DEITADO } from './viewport';

describe('matchMedia de teste', () => {
  it('começa em desktop: tela larga e mouse', () => {
    expect(window.matchMedia('(max-width: 720px)').matches).toBe(false);
    expect(window.matchMedia('(pointer: fine)').matches).toBe(true);
    expect(window.matchMedia('(hover: none)').matches).toBe(false);
    expect(window.innerWidth).toBe(1280);
  });

  it('avalia E, OU e orientação', () => {
    expect(avaliarConsulta('(pointer: coarse) and (max-height: 500px)', VIEWPORT_CELULAR_DEITADO)).toBe(true);
    expect(avaliarConsulta('(pointer: coarse) and (max-height: 500px)', VIEWPORT_CELULAR)).toBe(false);
    expect(avaliarConsulta('(orientation: portrait)', VIEWPORT_CELULAR)).toBe(true);
    expect(avaliarConsulta('(min-width: 2000px), (pointer: coarse)', VIEWPORT_CELULAR)).toBe(true);
  });

  it('girar o aparelho avisa quem ouve a consulta que virou — e só ela', () => {
    const estreita = window.matchMedia('(max-width: 720px)');
    const toque = window.matchMedia('(pointer: coarse)');
    const ouvidos: string[] = [];
    estreita.addEventListener('change', e => ouvidos.push(`estreita:${e.matches}`));
    toque.addEventListener('change', e => ouvidos.push(`toque:${e.matches}`));

    definirViewport(VIEWPORT_CELULAR);
    expect(ouvidos).toEqual(['estreita:true', 'toque:true']);

    definirViewport({ largura: 400 }); // continua estreita: ninguém é avisado
    expect(ouvidos).toHaveLength(2);
    expect(window.innerWidth).toBe(400);
  });
});
