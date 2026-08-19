import { memo, useEffect, useRef, useState } from 'react';
import type { ConversationSummary } from '../../api/conversations';
import type { Folder } from '../../api/folders';
import { ConvItem } from './ConvItem';
import { ctxItemStyle } from './styles';

interface FolderRowProps {
  folder: Folder;
  conversations: ConversationSummary[];
  activeId?: string;
  allFolders: Folder[];
  onSelect: (id: string) => void;
  onMove: (convId: string, folderId: string | null) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onNewInFolder: (folderId: string, folderName: string) => void;
  selectedConvIds?: Set<string>;
  selectionMode?: boolean;
  onToggleSelect?: (convId: string) => void;
  onDragStart?: (convId: string) => void;
  onDropConv?: (folderId: string | null) => void;
}

function FolderRowBase({ folder, conversations, activeId, allFolders, onSelect, onMove, onRename, onDelete, onNewInFolder, selectedConvIds, selectionMode, onToggleSelect, onDragStart, onDropConv }: FolderRowProps) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(folder.name);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  function submitRename() {
    const trimmed = editName.trim();
    if (trimmed && trimmed !== folder.name) onRename(folder.id, trimmed);
    setEditing(false);
  }

  return (
    <div style={{ marginBottom: 2 }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 2, padding: '3px 4px', borderRadius: 6, background: dragOver ? 'var(--fill2)' : 'transparent', transition: 'background 0.1s' }}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); onDropConv?.(folder.id); }}
      >
        <button
          onClick={() => setOpen(o => !o)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', padding: '2px 4px', display: 'flex', alignItems: 'center', gap: 5, flex: 1, minWidth: 0 }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none"
            style={{ flexShrink: 0, transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}>
            <path d="M3 2 L7 5 L3 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
            <path d="M2 4h5l1.5 2H14v7H2V4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill="var(--fill2)" />
          </svg>
          {editing ? (
            <input
              ref={inputRef}
              value={editName}
              onChange={e => setEditName(e.target.value)}
              onBlur={submitRename}
              onKeyDown={e => { if (e.key === 'Enter') submitRename(); if (e.key === 'Escape') { setEditName(folder.name); setEditing(false); } }}
              onClick={e => e.stopPropagation()}
              style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)', background: 'transparent', border: 'none', outline: '1px solid var(--green)', borderRadius: 3, padding: '0 3px', minWidth: 0, width: '100%' }}
            />
          ) : (
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {folder.name}
            </span>
          )}
        </button>

        <button
          onClick={e => { e.stopPropagation(); onNewInFolder(folder.id, folder.name); }}
          title="Nova consulta nesta pasta"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', padding: '2px 3px', borderRadius: 4, display: 'flex', alignItems: 'center', flexShrink: 0 }}
        >
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
            <path d="M8 3 V13 M3 8 H13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>

        <div ref={menuRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button
            onClick={e => { e.stopPropagation(); setMenuOpen(o => !o); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', padding: '2px 3px', borderRadius: 4, display: 'flex', alignItems: 'center' }}
          >
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="3" r="1.3" fill="currentColor" />
              <circle cx="8" cy="8" r="1.3" fill="currentColor" />
              <circle cx="8" cy="13" r="1.3" fill="currentColor" />
            </svg>
          </button>
          {menuOpen && (
            <div style={{
              position: 'absolute', right: 0, top: 'calc(100% + 2px)',
              background: 'var(--paper)', border: '1px solid var(--line2)',
              borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
              zIndex: 400, minWidth: 150, overflow: 'hidden',
            }}>
              <button onClick={() => { setEditing(true); setMenuOpen(false); }} style={ctxItemStyle}>
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                  <path d="M11 2 L14 5 L5 14 H2 V11 L11 2Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
                </svg>
                Renomear
              </button>
              <div style={{ height: 1, background: 'var(--line2)', margin: '0 8px' }} />
              {!confirmDelete ? (
                <button onClick={() => setConfirmDelete(true)} style={{ ...ctxItemStyle, color: '#ef4444' }}>
                  <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                    <path d="M3 5h10M6 5V3h4v2M6 8v5M10 8v5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                  </svg>
                  Excluir pasta
                </button>
              ) : (
                <div style={{ padding: '8px 12px' }}>
                  <p style={{ fontSize: 11.5, color: 'var(--ink)', margin: '0 0 6px', lineHeight: 1.4 }}>
                    {conversations.length > 0
                      ? `${conversations.length} conversa${conversations.length > 1 ? 's' : ''} voltará${conversations.length > 1 ? 'ão' : ''} para "Sem pasta".`
                      : 'Confirmar exclusão?'
                    }
                  </p>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => { onDelete(folder.id); setMenuOpen(false); setConfirmDelete(false); }}
                      style={{ flex: 1, fontSize: 11.5, padding: '4px 0', borderRadius: 5, border: 'none', background: '#ef4444', color: '#fff', cursor: 'pointer', fontWeight: 600 }}
                    >Excluir</button>
                    <button
                      onClick={() => setConfirmDelete(false)}
                      style={{ flex: 1, fontSize: 11.5, padding: '4px 0', borderRadius: 5, border: '1px solid var(--line2)', background: '#fff', color: 'var(--ink)', cursor: 'pointer' }}
                    >Cancelar</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {open && (
        <div style={{ paddingLeft: 12 }}>
          {conversations.length === 0 ? (
            <div style={{ fontSize: 11, color: 'var(--pen3)', padding: '4px 10px' }}>Vazia</div>
          ) : (
            conversations.map(conv => (
              <ConvItem
                key={conv.id}
                conv={conv}
                activeId={activeId}
                folders={allFolders}
                onSelect={onSelect}
                onMove={onMove}
                selected={selectedConvIds?.has(conv.id)}
                selectionMode={selectionMode}
                onToggleSelect={onToggleSelect}
                onDragStart={onDragStart}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

export const FolderRow = memo(FolderRowBase);
