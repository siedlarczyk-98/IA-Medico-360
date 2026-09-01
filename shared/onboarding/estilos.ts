/**
 * Paleta e estilos do onboarding compartilhado.
 *
 * Valores literais em vez de `var(--petrol)` porque os três apps não
 * compartilham design tokens: `frontend-app` e `calculadoras-app` definem as
 * variáveis no `index.css`, o `noticias-app` não define nenhuma. Um componente
 * que dependesse delas renderizaria sem estilo em um dos três — e o onboarding
 * é justamente a tela que precisa parecer a mesma em qualquer porta de entrada.
 *
 * As cores são cópia fiel do `:root` do `frontend-app`. Se aquele arquivo mudar,
 * este precisa mudar junto — é o custo de não ter tokens compartilhados.
 */

import type { CSSProperties } from 'react';

export const CORES = {
  ink: '#0e252d',
  petrol: '#014751',
  green: '#00d17d',
  mint: '#aef6c6',
  paper: '#fdfff4',
  pen: '#37464d',
  pen2: '#6b7a80',
  pen3: '#9aa6ab',
  line: '#d8ddde',
  line2: '#e7ebec',
  fill: '#eef2f1',
  fill2: '#f5f7f6',
  red: '#c8434b',
} as const;

// A fonte do produto, com as dos outros apps como degraus antes do fallback do
// sistema: o `noticias-app` carrega 'Just Sans', o `frontend-app` carrega
// 'Plus Jakarta Sans'. A que estiver disponível ganha.
export const FONTE =
  "'Plus Jakarta Sans', 'Just Sans', system-ui, -apple-system, 'Segoe UI', sans-serif";

export const fundo: CSSProperties = {
  // `100dvh` em vez de `100vh`: no iPhone dentro do iframe do LMS, a barra do
  // navegador entra na conta de `vh` e corta o botão.
  minHeight: '100dvh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: CORES.paper,
  padding: '32px 20px',
  boxSizing: 'border-box',
  fontFamily: FONTE,
};

export const cartao: CSSProperties = {
  width: '100%',
  maxWidth: 456,
  background: '#fff',
  border: `1px solid ${CORES.line2}`,
  borderRadius: 20,
  padding: '30px 30px 26px',
  boxShadow: '0 1px 2px rgba(14,37,45,.04), 0 12px 32px -12px rgba(14,37,45,.12)',
  color: CORES.ink,
  boxSizing: 'border-box',
};

export const titulo: CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  letterSpacing: '-0.02em',
  margin: '0 0 6px',
};

export const subtitulo: CSSProperties = {
  fontSize: 14,
  color: CORES.pen2,
  margin: '0 0 22px',
  lineHeight: 1.5,
};

export const rotulo: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: CORES.pen3,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  display: 'block',
  marginBottom: 8,
};

export const campo: CSSProperties = {
  width: '100%',
  padding: '12px 14px',
  border: `1px solid ${CORES.line}`,
  borderRadius: 10,
  fontSize: 14.5,
  color: CORES.ink,
  outline: 'none',
  background: '#fff',
  boxSizing: 'border-box',
  fontFamily: 'inherit',
};

/** Cartão de escolha do momento da carreira. */
export const opcao = (selecionada: boolean): CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  width: '100%',
  padding: '11px 14px',
  border: `1.5px solid ${selecionada ? CORES.petrol : CORES.line}`,
  background: selecionada ? CORES.fill : '#fff',
  borderRadius: 12,
  fontSize: 14.5,
  fontWeight: selecionada ? 600 : 500,
  color: selecionada ? CORES.petrol : CORES.pen,
  cursor: 'pointer',
  textAlign: 'left',
  fontFamily: 'inherit',
  transition: 'border-color .12s, background .12s',
});

/** O ponto que mostra a seleção — sem ele os cartões parecem campos desabilitados. */
export const marcador = (selecionada: boolean): CSSProperties => ({
  flexShrink: 0,
  width: 18,
  height: 18,
  borderRadius: '50%',
  border: `1.5px solid ${selecionada ? CORES.petrol : CORES.line}`,
  background: selecionada ? CORES.petrol : '#fff',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
});

export const marcadorInterno: CSSProperties = {
  width: 6,
  height: 6,
  borderRadius: '50%',
  background: CORES.green,
};

export const botao = (habilitado: boolean): CSSProperties => ({
  width: '100%',
  padding: '13px 16px',
  border: 'none',
  borderRadius: 12,
  fontSize: 15,
  fontWeight: 700,
  letterSpacing: '-0.01em',
  color: habilitado ? '#fff' : CORES.pen3,
  background: habilitado ? CORES.petrol : CORES.line2,
  cursor: habilitado ? 'pointer' : 'not-allowed',
  fontFamily: 'inherit',
  transition: 'background .12s',
});

export const aceite: CSSProperties = {
  display: 'flex',
  gap: 11,
  alignItems: 'flex-start',
  fontSize: 13,
  lineHeight: 1.5,
  color: CORES.pen,
  margin: '2px 0 18px',
  cursor: 'pointer',
};

export const link: CSSProperties = {
  color: CORES.petrol,
  fontWeight: 600,
  textDecoration: 'underline',
  textUnderlineOffset: 2,
};

export const erro: CSSProperties = {
  fontSize: 13,
  color: CORES.red,
  background: '#fdf2f3',
  border: '1px solid #f3d7d9',
  borderRadius: 10,
  padding: '10px 12px',
  margin: '0 0 16px',
};

/**
 * Hover e foco não existem em style inline — precisam de CSS de verdade.
 * Injetado uma vez pelo componente; escopado por prefixo para não vazar.
 */
export const CSS_GLOBAL = `
.m360-ob-opcao:hover { border-color: ${CORES.pen3}; }
.m360-ob-campo:focus { border-color: ${CORES.petrol}; box-shadow: 0 0 0 3px ${CORES.mint}55; }
.m360-ob-botao:not(:disabled):hover { background: ${CORES.ink}; }
.m360-ob-check { accent-color: ${CORES.petrol}; width: 17px; height: 17px; margin-top: 1px; flex-shrink: 0; }
`;
