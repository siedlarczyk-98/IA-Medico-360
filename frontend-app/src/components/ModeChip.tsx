import type { ReactElement } from 'react';

const icons: Record<string, ReactElement> = {
  raciocinio: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M8 1.5 C5 1.5 3.5 3.5 3.5 5.5 C3.5 7 2 7.5 2 9 C2 10.5 3.5 11 3.5 12.5 L3.5 14 L12.5 14 L12.5 12.5 C12.5 11 14 10.5 14 9 C14 7.5 12.5 7 12.5 5.5 C12.5 3.5 11 1.5 8 1.5 Z"
            stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" fill="none" />
    </svg>
  ),
  farmaco: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="5" width="12" height="6" rx="3" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 5 V11" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  ),
  busca: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10.5 10.5 L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  produtividade: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2.5" y="3" width="11" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5 6 H11 M5 8.5 H11 M5 11 H8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  exames: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <rect x="2.5" y="2" width="11" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="8" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5 11.5 H11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  dados: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <ellipse cx="8" cy="4" rx="5.5" ry="2" stroke="currentColor" strokeWidth="1.4" />
      <path d="M2.5 4 V12 C2.5 13.1 5 14 8 14 C11 14 13.5 13.1 13.5 12 V4" stroke="currentColor" strokeWidth="1.4" />
      <path d="M2.5 8 C2.5 9.1 5 10 8 10 C11 10 13.5 9.1 13.5 8" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  ),
};

const labels: Record<string, string> = {
  raciocinio:   'Raciocínio Clínico',
  farmaco:      'Checagem Farmacológica',
  busca:        'Busca Rápida',
  produtividade:'Produtividade',
  exames:       'Exames',
  dados:        'Dados do Brasil',
};

interface Props {
  mode: string;
  confidence?: number;
}

export function ModeChip({ mode, confidence }: Props) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 10px', fontSize: 11, fontWeight: 600,
      color: 'var(--petrol)', background: 'var(--mint)', borderRadius: 999,
    }}>
      <span style={{ color: 'var(--petrol)', display: 'flex' }}>{icons[mode]}</span>
      {labels[mode] ?? mode}
      {confidence != null && (
        <span style={{ color: 'var(--pen2)', fontWeight: 500, opacity: 0.7 }}>· {confidence}%</span>
      )}
    </span>
  );
}
