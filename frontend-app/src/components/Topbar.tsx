import { useEffect, useState } from 'react';

interface Props {
  title: string;
  mode: 'orquestrador' | 'agregador';
  onModeChange: (m: 'orquestrador' | 'agregador') => void;
  onMenuToggle: () => void;
}

function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.innerWidth <= 700);
  useEffect(() => {
    const handler = () => setMobile(window.innerWidth <= 700);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);
  return mobile;
}

export function Topbar({ title, mode, onModeChange, onMenuToggle }: Props) {
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

      <div style={{
        display: 'flex', background: 'var(--fill2)', padding: 3,
        borderRadius: 8, fontSize: 11, fontWeight: 600, flexShrink: 0,
      }}>
        {(['orquestrador', 'agregador'] as const).map(m => (
          <button
            key={m}
            onClick={() => onModeChange(m)}
            style={{
              padding: isMobile ? '5px 8px' : '5px 12px', border: 'none',
              borderRadius: 6,
              background: mode === m ? 'var(--paper)' : 'transparent',
              color: mode === m ? 'var(--ink)' : 'var(--pen2)',
              boxShadow: mode === m ? '0 1px 2px rgba(0,0,0,0.04)' : 'none',
              display: 'flex', alignItems: 'center', gap: 5,
              transition: 'background 0.15s', cursor: 'pointer',
              fontSize: isMobile ? 10 : 11,
            }}
          >
            {m === 'orquestrador' && mode === 'orquestrador' && (
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--green)', flexShrink: 0 }} />
            )}
            {m === 'orquestrador' ? 'Orquestrador' : 'Agregador'}
          </button>
        ))}
      </div>

    </header>
  );
}
