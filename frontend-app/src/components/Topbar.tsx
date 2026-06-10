import { useState } from 'react';
import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  title: string;
  mode: 'orquestrador' | 'agregador';
  onModeChange: (m: 'orquestrador' | 'agregador') => void;
  onMenuToggle: () => void;
}

const MODES = [
  {
    key: 'orquestrador' as const,
    label: 'Orquestrador',
    shortLabel: 'Orq.',
    icon: (
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.4" />
        <path d="M8 2 V4 M8 12 V14 M2 8 H4 M12 8 H14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M4.1 4.1 L5.5 5.5 M10.5 10.5 L11.9 11.9 M4.1 11.9 L5.5 10.5 M10.5 5.5 L11.9 4.1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
    ),
    desc: 'Respostas com validação em bases científicas e artigos. Escolha o modo ideal — busca rápida, raciocínio clínico, checagem farmacológica ou produtividade.',
  },
  {
    key: 'agregador' as const,
    label: 'Agregador',
    shortLabel: 'Agr.',
    icon: (
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="2" width="5" height="5" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
        <rect x="9" y="2" width="5" height="5" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
        <rect x="2" y="9" width="5" height="5" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
        <rect x="9" y="9" width="5" height="5" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    ),
    desc: 'Escolha a ferramenta que mais se adapta à sua necessidade. Acesse diretamente Claude, GPT, Gemini e outros — sem triagem automática.',
  },
] as const;

function ModeTooltip({ desc, visible }: { desc: string; visible: boolean }) {
  if (!visible) return null;
  return (
    <div style={{
      position: 'absolute', top: 'calc(100% + 8px)', right: 0, zIndex: 100,
      width: 220, background: 'var(--ink)', color: '#fff',
      fontSize: 11.5, lineHeight: 1.5, fontWeight: 400,
      padding: '9px 12px', borderRadius: 8,
      boxShadow: '0 4px 14px rgba(0,0,0,0.18)',
      pointerEvents: 'none',
    }}>
      <div style={{
        position: 'absolute', top: -5, right: 18,
        width: 10, height: 10, background: 'var(--ink)',
        transform: 'rotate(45deg)', borderRadius: 2,
      }} />
      {desc}
    </div>
  );
}

export function Topbar({ title, mode, onModeChange, onMenuToggle }: Props) {
  const isMobile = useIsMobile();
  const [tooltip, setTooltip] = useState<'orquestrador' | 'agregador' | null>(null);

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

      {/* Mode switcher */}
      <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
        {MODES.map(m => {
          const active = mode === m.key;
          return (
            <div
              key={m.key}
              style={{ position: 'relative' }}
              onMouseEnter={() => setTooltip(m.key)}
              onMouseLeave={() => setTooltip(null)}
            >
              <button
                onClick={() => onModeChange(m.key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: isMobile ? 4 : 6,
                  padding: isMobile ? '5px 8px' : '6px 12px',
                  border: `1.5px solid ${active ? 'var(--petrol)' : 'var(--line2)'}`,
                  borderRadius: 8,
                  background: active ? 'var(--petrol)' : '#fff',
                  color: active ? '#fff' : 'var(--pen2)',
                  fontWeight: 600, fontSize: isMobile ? 10 : 11,
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                <span style={{ opacity: active ? 1 : 0.6 }}>{m.icon}</span>
                {isMobile ? m.shortLabel : m.label}
                {/* Info hint */}
                <span style={{
                  width: 13, height: 13, borderRadius: '50%',
                  border: `1px solid ${active ? 'rgba(255,255,255,0.4)' : 'var(--line2)'}`,
                  fontSize: 9, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: active ? 'rgba(255,255,255,0.7)' : 'var(--pen3)',
                  flexShrink: 0,
                }}>?</span>
              </button>
              <ModeTooltip desc={m.desc} visible={tooltip === m.key} />
            </div>
          );
        })}
      </div>

    </header>
  );
}
