import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  title: string;
  onMenuToggle: () => void;
}

/**
 * O seletor de modos (Orquestrador / Agregador) foi removido junto com a
 * retirada do Agregador da interface: com um modo só, o switcher era um botão
 * que não levava a lugar nenhum. Ver git para o que havia aqui.
 */
export function Topbar({ title, onMenuToggle }: Props) {
  const isMobile = useIsMobile();

  return (
    <header style={{
      height: 54, borderBottom: '1px solid var(--line2)',
      display: 'flex', alignItems: 'center', padding: '0 16px', gap: 10,
      flexShrink: 0,
    }}>
      {isMobile && (
        <button
          onClick={onMenuToggle}
          style={{
            width: 34, height: 34, borderRadius: 8, border: '1px solid var(--line2)',
            background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--pen)', flexShrink: 0, cursor: 'pointer',
          }}
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <path d="M2 4 H14 M2 8 H14 M2 12 H14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      )}

      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {title}
        </span>
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--pen3)', opacity: 0.6, flexShrink: 0 }}>
          <path d="M11 3 L4 10 L3 13 L6 12 L13 5 Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" fill="none" />
        </svg>
      </div>
    </header>
  );
}
