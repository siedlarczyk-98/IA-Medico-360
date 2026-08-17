import { APP_MODES, type AppMode } from '../lib/appModes';
import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  userName?: string | null;
  onChoose: (mode: AppMode) => void;
}

export function ModeIntro({ userName, onChoose }: Props) {
  const isMobile = useIsMobile();

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: isMobile ? '0 20px' : '0 40px',
    }}>
      <div style={{ width: 720, maxWidth: '100%' }}>
        <div style={{ fontSize: isMobile ? 22 : 28, fontWeight: 700, color: 'var(--ink)', letterSpacing: -0.5 }}>
          {userName ? `Bem-vindo, ${userName}.` : 'Bem-vindo.'}
        </div>
        <div style={{ fontSize: 14, color: 'var(--pen2)', marginTop: 6, marginBottom: 24 }}>
          Antes de começar, escolha como você quer usar a plataforma. Você pode trocar isso a qualquer momento no topo da tela.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14 }}>
          {APP_MODES.map(m => (
            <button
              key={m.key}
              onClick={() => onChoose(m.key)}
              style={{
                textAlign: 'left', cursor: 'pointer', border: '1.5px solid var(--line2)',
                borderRadius: 14, padding: '18px 18px 16px', background: '#fff',
                display: 'flex', flexDirection: 'column', gap: 10,
                transition: 'border-color 0.15s, box-shadow 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--petrol)'; e.currentTarget.style.boxShadow = '0 4px 14px rgba(14,37,45,0.08)'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--line2)'; e.currentTarget.style.boxShadow = 'none'; }}
            >
              <div>
                <span style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase',
                  color: 'var(--petrol)', background: 'var(--mint)', borderRadius: 999, padding: '3px 9px',
                }}>
                  {m.tagline}
                </span>
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>{m.label}</div>
              <div style={{ fontSize: 12.5, color: 'var(--pen2)', lineHeight: 1.5 }}>{m.desc}</div>
              <ul style={{ margin: '4px 0 0', paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {m.bullets.map((b, i) => (
                  <li key={i} style={{ fontSize: 12, color: 'var(--pen)', lineHeight: 1.4 }}>{b}</li>
                ))}
              </ul>
              <div style={{
                marginTop: 8, alignSelf: 'flex-start', fontSize: 12, fontWeight: 700, color: 'var(--petrol)',
                display: 'flex', alignItems: 'center', gap: 4,
              }}>
                Usar {m.label}
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                  <path d="M3 8 H13 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
