/**
 * Conversão de unidade do perfil lipídico, compartilhada pelo passo PREVENT do
 * wizard SBC 2025 e pela calculadora PREVENT avulsa.
 *
 * O MDCalc abre o PREVENT em mmol/L com alternador de unidade. Aqui o canônico
 * é mg/dL (o que o backend recebe e o que o laboratório brasileiro reporta); a
 * unidade é só de exibição. Constante idêntica à `mmol_conversion` da AHA.
 */
export const MMOL_POR_MGDL = 0.02586;

export type UnidadeLipides = 'mgdl' | 'mmoll';

export const rotuloUnidade = (u: UnidadeLipides) => (u === 'mgdl' ? 'mg/dL' : 'mmol/L');

/** mg/dL guardado no estado -> string exibida na unidade escolhida. */
export const paraExibicao = (mgdl: string, unidade: UnidadeLipides): string => {
  const n = parseFloat(mgdl);
  if (isNaN(n)) return '';
  return unidade === 'mmoll' ? (n * MMOL_POR_MGDL).toFixed(2) : String(n);
};

/** String digitada na unidade escolhida -> mg/dL para o estado. */
export const paraMgdl = (digitado: string, unidade: UnidadeLipides): string => {
  if (unidade === 'mgdl') return digitado;
  const n = parseFloat(digitado.replace(',', '.'));
  if (isNaN(n)) return '';
  return (n / MMOL_POR_MGDL).toFixed(1);
};
