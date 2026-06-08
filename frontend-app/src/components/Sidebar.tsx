import { useEffect, useRef, useState } from 'react';
import { Logo } from './Logo';
import { useCurrentUser } from '../lib/useCurrentUser';
import { useUserUsage } from '../lib/useUserUsage';
import { listConversations, type ConversationSummary } from '../api/conversations';
import { logout } from '../lib/auth';
import { ProfileModal } from './ProfileModal';

interface Props {
  activeId?: string;
  onNew: () => void;
  onSelect: (id: string) => void;
  open: boolean;
  onToggle: () => void;
  usageTick?: number;
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

function groupByDate(conversations: ConversationSummary[]) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);

  const groups: { label: string; items: ConversationSummary[] }[] = [
    { label: 'Hoje', items: [] },
    { label: 'Esta semana', items: [] },
    { label: 'Anteriores', items: [] },
  ];

  for (const conv of conversations) {
    const d = new Date(conv.updatedat);
    d.setHours(0, 0, 0, 0);
    if (d >= today) groups[0].items.push(conv);
    else if (d >= weekAgo) groups[1].items.push(conv);
    else groups[2].items.push(conv);
  }

  return groups.filter(g => g.items.length > 0);
}

export function Sidebar({ activeId, onNew, onSelect, open, onToggle, usageTick = 0 }: Props) {
  const isMobile = useIsMobile();
  const user = useCurrentUser();
  const usage = useUserUsage(usageTick);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [showUsageTip, setShowUsageTip] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [, setProfileTick] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listConversations()
      .then(setConversations)
      .catch(() => {});
  }, [activeId]); // refetch when a new conversation is created

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

  if (isMobile && !open) return null;

  const closeAfter = (fn: () => void) => () => { fn(); if (isMobile) onToggle(); };
  const groups = groupByDate(conversations);

  const aside = (
    <aside style={{
      width: 260, flexShrink: 0, height: '100%',
      borderRight: '1px solid var(--line2)',
      display: 'flex', flexDirection: 'column',
      background: '#fbfdf7',
      ...(isMobile ? {
        position: 'fixed', left: 0, top: 0, bottom: 0,
        height: '100dvh', zIndex: 200,
        boxShadow: '2px 0 20px rgba(0,0,0,0.15)',
      } : {}),
    }}>
      <div style={{ padding: '18px 18px 8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Logo />
        {isMobile && (
          <button onClick={onToggle} style={{
            background: 'none', border: 'none',
            color: 'var(--pen3)', cursor: 'pointer', padding: 4,
            display: 'flex', alignItems: 'center',
          }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        )}
      </div>

      <div style={{ padding: '10px 14px' }}>
        <button
          onClick={closeAfter(onNew)}
          style={{
            width: '100%', background: 'var(--ink)', color: '#fff',
            border: 'none', borderRadius: 10, padding: '10px 12px',
            fontSize: 13, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center',
            cursor: 'pointer',
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
        {groups.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <p style={{ fontSize: 12, color: 'var(--pen3)', textAlign: 'center', padding: '0 16px' }}>
              Nenhuma consulta anterior
            </p>
          </div>
        ) : (
          groups.map(group => (
            <div key={group.label} style={{ marginBottom: 14 }}>
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: 1.2,
                textTransform: 'uppercase', color: 'var(--pen3)', padding: '6px 10px',
              }}>{group.label}</div>
              {group.items.map(conv => (
                <div
                  key={conv.id}
                  onClick={closeAfter(() => onSelect(conv.id))}
                  style={{
                    padding: '7px 10px', fontSize: 12.5, color: 'var(--pen)',
                    borderRadius: 6, cursor: 'pointer',
                    background: conv.id === activeId ? 'var(--mint)' : 'transparent',
                    fontWeight: conv.id === activeId ? 600 : 400,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => { if (conv.id !== activeId) (e.currentTarget as HTMLElement).style.background = 'var(--fill)'; }}
                  onMouseLeave={e => { if (conv.id !== activeId) (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                  title={conv.title ?? ''}
                >
                  {conv.title ?? 'Sem título'}
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      {usage.hasLimit && !usage.loading && (
        <div style={{ padding: '10px 14px 2px' }}>
          {(() => {
            const pct = usage.usagePercentage ?? 0;
            const barColor = pct >= 80 ? '#f87171' : pct >= 50 ? '#facc15' : '#4ade80';
            const daysLeft = usage.weekResetAt
              ? Math.max(0, Math.ceil((usage.weekResetAt.getTime() - Date.now()) / 86400000))
              : null;
            return (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, position: 'relative' }}>
                    <span style={{ fontSize: 10, color: 'var(--pen3)', fontWeight: 600, letterSpacing: 0.5 }}>
                      LIMITE SEMANAL
                    </span>
                    <span
                      onMouseEnter={() => setShowUsageTip(true)}
                      onMouseLeave={() => setShowUsageTip(false)}
                      style={{ display: 'flex', alignItems: 'center', color: 'var(--pen3)', cursor: 'default' }}
                    >
                      <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.4" />
                        <path d="M8 7 V11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        <circle cx="8" cy="5" r="0.9" fill="currentColor" />
                      </svg>
                    </span>
                    {showUsageTip && (
                      <div style={{
                        position: 'absolute', bottom: 'calc(100% + 6px)', left: 0,
                        width: 210, background: 'var(--ink)', color: '#fff',
                        fontSize: 11, lineHeight: 1.5, padding: '8px 10px',
                        borderRadius: 8, zIndex: 300, pointerEvents: 'none',
                        boxShadow: '0 4px 12px rgba(0,0,0,0.18)',
                      }}>
                        Seu plano inclui uma cota semanal de uso de inteligência artificial. O limite reinicia automaticamente toda semana.
                      </div>
                    )}
                  </div>
                  <span style={{ fontSize: 10, color: 'var(--pen3)' }}>
                    {pct >= 100
                      ? daysLeft !== null ? `Renova em ${daysLeft}d` : 'Limite atingido'
                      : `${pct}%`}
                  </span>
                </div>
                <div style={{ height: 4, borderRadius: 4, background: 'var(--line2)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${pct}%`, background: barColor, borderRadius: 4, transition: 'width 0.4s' }} />
                </div>
              </>
            );
          })()}
        </div>
      )}

      <div ref={menuRef} style={{ borderTop: '1px solid var(--line2)', padding: '12px 14px', position: 'relative' }}>
        {menuOpen && (
          <div style={{
            position: 'absolute', bottom: 'calc(100% + 4px)', left: 14, right: 14,
            background: 'var(--paper)', border: '1px solid var(--line2)',
            borderRadius: 10, boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            overflow: 'hidden', zIndex: 300,
          }}>
            <button
              onClick={() => { setMenuOpen(false); setShowProfile(true); }}
              style={menuItemStyle}
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="6" r="3" stroke="currentColor" strokeWidth="1.4" />
                <path d="M2 14c0-2.5 2.7-4 6-4s6 1.5 6 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
              Editar perfil
            </button>
            <div style={{ height: 1, background: 'var(--line2)', margin: '0 10px' }} />
            <button
              onClick={logout}
              style={{ ...menuItemStyle, color: '#ef4444' }}
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path d="M10 11 L14 8 L10 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M14 8 H6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                <path d="M6 3 H3 V13 H6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Sair
            </button>
          </div>
        )}

        <div
          onClick={() => setMenuOpen(o => !o)}
          style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', borderRadius: 8, padding: '2px 4px', transition: 'background 0.1s' }}
          onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--fill)'}
          onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
        >
          <div style={{
            width: 32, height: 32, borderRadius: '50%', background: 'var(--mint)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 600, color: 'var(--pen2)', flexShrink: 0,
          }}>{user?.initial ?? '?'}</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {user?.name ?? '—'}
            </div>
            <div style={{ fontSize: 10.5, color: 'var(--pen2)' }}>
              {[user?.crmLabel, user?.medStatusLabel].filter(Boolean).join(' · ') || 'Beta'}
            </div>
          </div>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--pen3)', flexShrink: 0 }}>
            <circle cx="8" cy="4" r="1.2" fill="currentColor" />
            <circle cx="8" cy="8" r="1.2" fill="currentColor" />
            <circle cx="8" cy="12" r="1.2" fill="currentColor" />
          </svg>
        </div>
      </div>

      {showProfile && (
        <ProfileModal
          onClose={() => setShowProfile(false)}
          onSuccess={() => setProfileTick(t => t + 1)}
        />
      )}
    </aside>
  );

  if (!isMobile) return aside;

  return (
    <>
      <div
        onClick={onToggle}
        style={{ position: 'fixed', inset: 0, zIndex: 199, background: 'rgba(0,0,0,0.35)' }}
      />
      {aside}
    </>
  );
}

const menuItemStyle: React.CSSProperties = {
  width: '100%', display: 'flex', alignItems: 'center', gap: 9,
  padding: '10px 14px', background: 'none', border: 'none',
  fontSize: 13, color: 'var(--ink)', cursor: 'pointer', textAlign: 'left',
};
