/** Texto digitado num campo numérico → número (ver `CampoNumerico`). */

/** Deixa só o que forma um número: dígitos e, se `decimal`, um separador (vira ponto). */
export function normalizarNumero(digitado: string, decimal: boolean): string {
  const s = digitado.replace(/,/g, '.').replace(decimal ? /[^\d.]/g : /\D/g, '');
  const ponto = s.indexOf('.');
  return ponto < 0 ? s : s.slice(0, ponto + 1) + s.slice(ponto + 1).replace(/\./g, '');
}

/** Os dois textos dizem o mesmo número? Vazio e "." contam como "nenhum". */
export function mesmoNumero(a: string, b: string): boolean {
  const n = (s: string) => (s === '' || s === '.' ? null : Number(s));
  return n(a) === n(b);
}
