import { memo, useEffect, useRef, useState } from 'react';
import type { ConversationSummary } from '../../api/conversations';
import type { Folder } from '../../api/folders';
import { ctxItemStyle } from './styles';

interface ConvItemProps {
  conv: ConversationSummary;
  activeId?: string;
  folders: Folder[];
  onSelect: (id: string) => void;
  onMove: (convId: string, folderId: string | null) => void;
  selected?: boolean;
  selectionMode?: boolean;
  onToggleSelect?: (convId: string) => void;
  onDragStart?: (convId: string) => void;
}

function ConvItemBase({ conv, activeId, folders, onSelect, onMove, selected, selectionMode, onToggleSelect, onDragStart }: ConvItemProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const [hovered, setHovered] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);
  const isActive = conv.id === activeId;
  const showBtn = hovered || menuOpen;

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (
        menuRef.current && !menuRef.current.contains(e.target as Node) &&
        dropRef.current && !dropRef.current.contains(e.target as Node)
      ) {
        setMenuOpen(false);
        setShowFolderPicker(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen || !btnRef.current || !dropRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const drop = dropRef.current;
    drop.style.top = (rect.bottom + 4) + 'px';
    drop.style.left = (rect.right - drop.offsetWidth) + 'px';
  }, [menuOpen]);

  const rowBg = selected ? 'var(--fill2)' : isActive ? 'var(--mint)' : hovered ? 'var(--fill)' : 'transparent';

  return (
    <div
      draggable
      onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; onDragStart?.(conv.id); }}
      style={{ position: 'relative', borderRadius: 6, background: rowBg, transition: 'background 0.1s', cursor: 'grab' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        onClick={() => selectionMode ? onToggleSelect?.(conv.id) : onSelect(conv.id)}
        style={{
          padding: '7px 10px',
          paddingLeft: (selectionMode || hovered) ? 6 : 10,
          paddingRight: showBtn ? 26 : 10,
          fontSize: 12.5,
          color: 'var(--pen)',
          cursor: 'pointer',
          fontWeight: isActive ? 600 : 400,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
        title={conv.title ?? ''}
      >
        {(selectionMode || hovered) && (
          <span
            onClick={e => { e.stopPropagation(); onToggleSelect?.(conv.id); }}
            style={{
              width: 14, height: 14, borderRadius: 3, border: `1.5px solid ${selected ? 'var(--green)' : 'var(--line2)'}`,
              background: selected ? 'var(--green)' : '#fff', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
              opacity: selectionMode || hovered ? 1 : 0,
            }}
          >
            {selected && <svg width="8" height="8" viewBox="0 0 10 10"><path d="M2 5 L4 7 L8 3" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" fill="none"/></svg>}
          </span>
        )}
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{conv.title ?? 'Sem título'}</span>
      </div>

      {showBtn && (
        <div ref={menuRef} style={{ position: 'absolute', right: 4, top: '50%', transform: 'translateY(-50%)' }}>
          <button
            ref={btnRef}
            onClick={e => { e.stopPropagation(); setMenuOpen(o => !o); setShowFolderPicker(false); }}
            style={{
              background: menuOpen ? 'var(--fill2)' : 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--pen2)',
              padding: '2px 4px',
              borderRadius: 4,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="3" r="1.3" fill="currentColor" />
              <circle cx="8" cy="8" r="1.3" fill="currentColor" />
              <circle cx="8" cy="13" r="1.3" fill="currentColor" />
            </svg>
          </button>
        </div>
      )}

      {menuOpen && (
        <div
          ref={dropRef}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            background: 'var(--paper)',
            border: '1px solid var(--line2)',
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.14)',
            zIndex: 500,
            minWidth: 170,
            overflow: 'hidden',
          }}
        >
          {!showFolderPicker ? (
            <div>
              <button
                onClick={e => { e.stopPropagation(); setShowFolderPicker(true); }}
                style={ctxItemStyle}
              >
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                  <path d="M2 4h5l1.5 2H14v7H2V4z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
                </svg>
                Mover para pasta
              </button>
              {conv.folder_id && (
                <button
                  onClick={e => { e.stopPropagation(); onMove(conv.id, null); setMenuOpen(false); }}
                  style={ctxItemStyle}
                >
                  <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                    <path d="M3 3L13 13M13 3L3 13" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                  </svg>
                  Remover da pasta
                </button>
              )}
            </div>
          ) : (
            <div>
              <div style={{ padding: '6px 12px 4px', fontSize: 10, fontWeight: 700, color: 'var(--pen3)', letterSpacing: 0.8, textTransform: 'uppercase' }}>
                Escolher pasta
              </div>
              {folders.length === 0 && (
                <div style={{ padding: '6px 12px', fontSize: 12, color: 'var(--pen3)' }}>Nenhuma pasta criada</div>
              )}
              {folders.map(f => (
                <button
                  key={f.id}
                  onClick={e => { e.stopPropagation(); onMove(conv.id, f.id); setMenuOpen(false); }}
                  style={{ ...ctxItemStyle, fontWeight: conv.folder_id === f.id ? 600 : 400 }}
                >
                  {conv.folder_id === f.id ? '✓ ' : ''}{f.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Memoizado: numa lista longa, sem isso qualquer estado local do Sidebar
// (hover, menu, usageTick) re-renderiza todos os itens.
export const ConvItem = memo(ConvItemBase);
