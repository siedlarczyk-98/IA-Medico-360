/**
 * Campo numérico que abre o TECLADO NUMÉRICO no celular.
 *
 * POR QUE NÃO `type="number"`
 * No iPhone, `type="number"` abre o teclado inteiro (com a fileira de números
 * em cima), e não o teclado numérico. `inputMode="decimal"` abre o numérico —
 * mas no iPhone em português a tecla decimal é a VÍRGULA, e um `type="number"`
 * pode recusar "7,5" em silêncio (o valor chega vazio). Por isso o campo é
 * texto: aceita vírgula ou ponto, mostra o que a pessoa digitou e entrega o
 * valor sempre com ponto, que é o que `Number()`/`parseFloat()` entendem.
 *
 * SEM SINAL DE MENOS
 * O teclado numérico do iPhone não tem a tecla "-". Campo que aceita negativo
 * NÃO usa este componente (ver `aceitaNegativo` no `FieldWidget`): continua
 * com `type="number"` e o teclado de números e pontuação.
 *
 * Faixa (mínimo/máximo) não é conferida aqui: quem confere é o backend
 * (`app/calculators/engine/validation.py`), com a mensagem certa.
 */

import { useState, type CSSProperties } from 'react';

import { mesmoNumero, normalizarNumero } from './numeroDigitado';

interface Props {
  id?: string;
  /** Valor atual, com ponto como separador ('' = vazio). */
  value: string;
  /** Recebe o valor normalizado: só dígitos e no máximo um ponto. */
  onChange: (valor: string) => void;
  decimal: boolean;
  placeholder?: string;
  style?: CSSProperties;
}

export function CampoNumerico({ id, value, onChange, decimal, placeholder, style }: Props) {
  // O que a pessoa digitou, com a vírgula dela e o "7," no meio do caminho. Só
  // é mostrado enquanto disser o mesmo número que `value`; se o valor mudou por
  // fora (preenchimento pela IA, troca de unidade, limpar), vale o de fora.
  const [digitado, setDigitado] = useState(value);
  const exibido = mesmoNumero(normalizarNumero(digitado, decimal), value)
    ? digitado
    : value.replace('.', ',');

  return (
    <input
      id={id}
      type="text"
      inputMode={decimal ? 'decimal' : 'numeric'}
      autoComplete="off"
      enterKeyHint="next"
      value={exibido}
      placeholder={placeholder}
      onChange={e => {
        const bruto = e.target.value;
        const limpo = normalizarNumero(bruto, decimal);
        // Mostra o número limpo, mas com o separador que a pessoa usou.
        const separador = bruto.match(/[.,]/)?.[0] ?? ',';
        setDigitado(limpo.replace('.', separador));
        onChange(limpo);
      }}
      style={style}
    />
  );
}
