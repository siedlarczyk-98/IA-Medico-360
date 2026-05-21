import { Logo } from './Logo';

interface Props {
  activeId?: string;
  onNew: () => void;
  onSelect: (id: string) => void;
  open: boolean;
  onToggle: () => void;
}

const history = {
  hoje: [
    { id: 'iam', label: 'IAM com supra — protocolo MOV' },
    { id: 'amox', label: 'Posologia amoxicilina pediátrica' },
    { id: 'cid', label: 'Dúvida CID I50.1' },
  ],
  semana: [
    { id: 'varf', label: 'Interação varfarina + amiodarona' },
    { id: 'has', label: 'Manejo HAS resistente' },
    { id: 'usg', label: 'Laudo USG transvaginal' },
    { id: 'email', label: 'Email retorno paciente Sra. R.' },
  ],
  anteriores: [
    { id: 'cef', label: 'Diferenciais cefaleia thunderclap' },
    { id: 'sep', label: 'Protocolo sepse neonatal' },
  ],
};

export function Sidebar({ activeId, onNew, onSelect, open, onToggle }: Props) {
  return (
    <>
      <style>{`
        .sidebar-overlay {
          display: none;
        }
        @media (max-width: 700px) {
          .sidebar {
            position: fixed !important;
            left: 0; top: 0; bottom: 0;
            z-index: 200;
            transform: translateX(-100%);
            transition: transform 0.22s ease;
            box-shadow: 2px 0 16px rgba(0,0,0,0.12);
          }
          .sidebar.open {
            transform: translateX(0);
          }
          .sidebar-overlay {
            display: block;
            position: fixed;
            inset: 0;
            z-index: 199;
            background: rgba(0,0,0,0.35);
          }
        }
      `}</style>

      {open && (
        <div className="sidebar-overlay" onClick={onToggle} />
      )}

      <aside className={`sidebar${open ? ' open' : ''}`} style={{
        width: 260, flexShrink: 0, height: '100%',
        borderRight: '1px solid var(--line2)',
        display: 'flex', flexDirection: 'column',
        background: '#fbfdf7',
      }}>
        <div style={{ padding: '18px 18px 8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Logo />
          <button
            onClick={onToggle}
            className="sidebar-close-btn"
            style={{
              display: 'none',
              background: 'none', border: 'none',
              color: 'var(--pen3)', cursor: 'pointer', padding: 4,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <style>{`
          @media (max-width: 700px) {
            .sidebar-close-btn { display: flex !important; }
          }
        `}</style>

        <div style={{ padding: '10px 14px' }}>
          <button
            onClick={() => { onNew(); if (open) onToggle(); }}
            style={{
              width: '100%', background: 'var(--ink)', color: '#fff',
              border: 'none', borderRadius: 10, padding: '10px 12px',
              fontSize: 13, fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center',
            }}
          >
            <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> Nova consulta
          </button>
        </div>

        <div style={{ padding: '4px 14px 12px' }}>
          <div style={{
            height: 30, borderRadius: 8, border: '1px solid var(--line2)',
            background: '#fff', display: 'flex', alignItems: 'center',
            padding: '0 10px', gap: 8, fontSize: 11, color: 'var(--pen3)',
          }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10.5 10.5 L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            Buscar conversas
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {(Object.entries({ Hoje: history.hoje, 'Esta semana': history.semana, Anteriores: history.anteriores }) as [string, typeof history.hoje][]).map(([group, items]) => (
            <div key={group} style={{ marginBottom: 14 }}>
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: 1.2,
                textTransform: 'uppercase', color: 'var(--pen3)', padding: '6px 10px',
              }}>{group}</div>
              {items.map(item => (
                <div
                  key={item.id}
                  onClick={() => { onSelect(item.id); if (open) onToggle(); }}
                  style={{
                    padding: '7px 10px', fontSize: 12.5, color: 'var(--pen)',
                    borderRadius: 6, cursor: 'pointer',
                    background: item.id === activeId ? 'var(--mint)' : 'transparent',
                    fontWeight: item.id === activeId ? 600 : 400,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    transition: 'background 0.1s',
                  }}
                >{item.label}</div>
              ))}
            </div>
          ))}
        </div>

        <div style={{
          borderTop: '1px solid var(--line2)', padding: '12px 14px',
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%', background: 'var(--mint)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 600, color: 'var(--pen2)', flexShrink: 0,
          }}>H</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink)' }}>Dra. Helena Vieira</div>
            <div style={{ fontSize: 10.5, color: 'var(--pen2)' }}>CRM/SP 184.523 · Cardiologia</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--pen3)', flexShrink: 0 }}>
            <circle cx="8" cy="4" r="1.2" fill="currentColor" />
            <circle cx="8" cy="8" r="1.2" fill="currentColor" />
            <circle cx="8" cy="12" r="1.2" fill="currentColor" />
          </svg>
        </div>
      </aside>
    </>
  );
}
