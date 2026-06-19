import type { CSSProperties } from 'react';

/**
 * Tokens de estilo compartilhados para padrões repetidos na UI.
 * Mantém a aparência idêntica — apenas centraliza os trechos inline duplicados.
 */

/** Base de "chip" (pílula com ícone + texto): anexos, status de upload, etc. */
export const chipBase: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '4px 10px',
  borderRadius: 8,
  fontSize: 11.5,
};

/** Chip neutro (fundo/borda padrão do tema). */
export const chipNeutral: CSSProperties = {
  ...chipBase,
  background: 'var(--fill2)',
  border: '1px solid var(--line2)',
  color: 'var(--pen2)',
};

/** Botão só-ícone (ações compactas, 30x30). */
export const iconButtonBase: CSSProperties = {
  height: 30,
  borderRadius: 8,
  border: '1px solid var(--line2)',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
  transition: 'all 0.12s',
};
