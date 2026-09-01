/**
 * Paleta própria, em vez de `var(--petrol)` e afins.
 *
 * Os três apps não compartilham design tokens: `frontend-app` e
 * `calculadoras-app` definem as variáveis no `index.css`, o `noticias-app` não
 * define nenhuma. Um componente compartilhado que dependesse delas renderizaria
 * sem estilo em um dos três — e o onboarding é justamente a tela que precisa
 * parecer a mesma em qualquer porta de entrada.
 *
 * Os valores espelham os tokens do `frontend-app`, para não destoar de onde a
 * tela já existia.
 */

import type { CSSProperties } from 'react';

export const CORES = {
  petrol: '#0f5c5c',
  ink: '#1a2b2b',
  pen: '#5a6b6b',
  line: '#dde5e5',
  paper: '#ffffff',
  fill: '#f4f8f6',
  red: '#c0392b',
} as const;

export const fundo: CSSProperties = {
  minHeight: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: CORES.fill,
  padding: 24,
  boxSizing: 'border-box',
};

export const cartao: CSSProperties = {
  width: '100%',
  maxWidth: 440,
  background: CORES.paper,
  border: `1px solid ${CORES.line}`,
  borderRadius: 16,
  padding: '36px 32px',
  fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  color: CORES.ink,
  boxSizing: 'border-box',
};

export const rotulo: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: CORES.pen,
  letterSpacing: '0.03em',
  display: 'block',
  marginBottom: 6,
};

export const campo: CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  border: `1px solid ${CORES.line}`,
  borderRadius: 8,
  fontSize: 14,
  color: CORES.ink,
  outline: 'none',
  background: CORES.paper,
  boxSizing: 'border-box',
  fontFamily: 'inherit',
};

export const botao = (habilitado: boolean): CSSProperties => ({
  width: '100%',
  padding: '12px 16px',
  border: 'none',
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 600,
  color: CORES.paper,
  background: habilitado ? CORES.petrol : CORES.line,
  cursor: habilitado ? 'pointer' : 'not-allowed',
  fontFamily: 'inherit',
});

export const opcao = (selecionada: boolean): CSSProperties => ({
  padding: '12px 14px',
  border: `1px solid ${selecionada ? CORES.petrol : CORES.line}`,
  background: selecionada ? CORES.fill : CORES.paper,
  borderRadius: 8,
  fontSize: 14,
  fontWeight: selecionada ? 600 : 400,
  color: CORES.ink,
  cursor: 'pointer',
  textAlign: 'left',
  fontFamily: 'inherit',
});
