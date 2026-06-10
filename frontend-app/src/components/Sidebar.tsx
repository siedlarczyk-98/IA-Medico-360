import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { Logo } from './Logo';
import { useCurrentUser } from '../lib/useCurrentUser';
import { useUserUsage } from '../lib/useUserUsage';
import { listConversations, type ConversationSummary } from '../api/conversations';
import { listFolders, createFolder, renameFolder, deleteFolder, moveConversation, type Folder } from '../api/folders';
import { logout } from '../lib/auth';
import { ProfileModal } from './ProfileModal';
import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  activeId?: string;
  onNew: () => void;
  onSelect: (id: string) => void;
  open: boolean;
  onToggle: () => void;
  usageTick?: number;
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
    if (conv.folder_id) continue; // pastas tratadas separadamente
    const d = new Date(conv.updatedat);
    d.setHours(0, 0, 0, 0);
    if (d >= today) groups[0].items.push(conv);
    else if (d >= weekAgo) groups[1].items.push(conv);
    else groups[2].items.push(conv);
  }

  return groups.filter(g => g.items.length > 0);
}

// ── Item de conversa com menu contextual ────────────────────────

interface ConvItemProps {
  conv: ConversationSummary;
  activeId?: string;
  folders: Folder[];
  onSelect: () => void;
  onMove: (folderId: string | null) => void;
}

function ConvItem({ conv, activeId, folders, onSelect, onMove }: ConvItemProps) {
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

  const rowBg = isActive ? 'var(--mint)' : hovered ? 'var(--fill)' : 'transparent';

  return (
    <div
      style={{ position: 'relative', borderRadius: 6, background: rowBg, transition: 'background 0.1s' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        onClick={onSelect}
        style={{
          padding: '7px 10px',
          paddingRight: showBtn ? 26 : 10,
          fontSize: 12.5,
          color: 'var(--pen)',
          cursor: 'pointer',
          fontWeight: isActive ? 600 : 400,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
        title={conv.title ?? ''}
      >
        {conv.title ?? 'Sem título'}
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
                  onClick={e => { e.stopPropagation(); onMove(null); setMenuOpen(false); }}
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
                  onClick={e => { e.stopPropagation(); onMove(f.id); setMenuOpen(false); }}
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

const ctxItemStyle: React.CSSProperties = {
  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
  padding: '8px 12px', background: 'none', border: 'none',
  fontSize: 12.5, color: 'var(--ink)', cursor: 'pointer', textAlign: 'left',
};

// ── Linha de pasta ───────────────────────────────────────────────

interface FolderRowProps {
  folder: Folder;
  conversations: ConversationSummary[];
  activeId?: string;
  allFolders: Folder[];
  onSelect: (id: string) => void;
  onMove: (convId: string, folderId: string | null) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
}

function FolderRow({ folder, conversations, activeId, allFolders, onSelect, onMove, onRename, onDelete }: FolderRowProps) {
  const [open, setOpen] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(folder.name);
  const [menuOpen, setMenuOpen] = useState(false);
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 2, padding: '3px 4px', borderRadius: 6 }}>
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
              <button onClick={() => { onDelete(folder.id); setMenuOpen(false); }} style={{ ...ctxItemStyle, color: '#ef4444' }}>
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                  <path d="M3 5h10M6 5V3h4v2M6 8v5M10 8v5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
                Excluir pasta
              </button>
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
                onSelect={() => onSelect(conv.id)}
                onMove={fId => onMove(conv.id, fId)}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Sidebar principal ────────────────────────────────────────────

function SidebarComponent({ activeId, onNew, onSelect, open, onToggle, usageTick = 0 }: Props) {
  const isMobile = useIsMobile();
  const user = useCurrentUser();
  const usage = useUserUsage(usageTick);
  const queryClient = useQueryClient();

  const { data: conversations = [] } = useQuery<ConversationSummary[]>({
    queryKey: ['conversations'],
    queryFn: listConversations,
    staleTime: 60_000,
  });

  const { data: folders = [] } = useQuery<Folder[]>({
    queryKey: ['folders'],
    queryFn: listFolders,
    staleTime: 60_000,
  });

  const createFolderMutation = useMutation({
    mutationFn: (name: string) => createFolder(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['folders'] }),
  });

  const renameFolderMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameFolder(id, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['folders'] }),
  });

  const deleteFolderMutation = useMutation({
    mutationFn: (id: string) => deleteFolder(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['folders'] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });

  const moveConvMutation = useMutation({
    mutationFn: ({ convId, folderId }: { convId: string; folderId: string | null }) =>
      moveConversation(convId, folderId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  });

  const [showUsageTip, setShowUsageTip] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [, setProfileTick] = useState(0);
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const newFolderInputRef = useRef<HTMLInputElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activeId && !conversations.some(c => c.id === activeId)) {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    }
  }, [activeId, conversations, queryClient]);

  useEffect(() => {
    if (!userMenuOpen) return;
    function handleClick(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) setUserMenuOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [userMenuOpen]);

  useEffect(() => {
    if (creatingFolder) newFolderInputRef.current?.focus();
  }, [creatingFolder]);

  const closeAfter = useCallback(
    (fn: () => void) => () => { fn(); if (isMobile) onToggle(); },
    [isMobile, onToggle],
  );

  const groups = useMemo(() => groupByDate(conversations), [conversations]);

  const convsByFolder = useMemo(() => {
    const map: Record<string, ConversationSummary[]> = {};
    for (const f of folders) map[f.id] = [];
    for (const c of conversations) {
      if (c.folder_id && map[c.folder_id]) map[c.folder_id].push(c);
    }
    return map;
  }, [folders, conversations]);

  function submitNewFolder() {
    const name = newFolderName.trim();
    if (name) createFolderMutation.mutate(name);
    setNewFolderName('');
    setCreatingFolder(false);
  }

  if (isMobile && !open) return null;

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
          <button onClick={onToggle} style={{ background: 'none', border: 'none', color: 'var(--pen3)', cursor: 'pointer', padding: 4, display: 'flex', alignItems: 'center' }}>
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

        {/* Seção de pastas */}
        {(folders.length > 0 || creatingFolder) && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px' }}>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.2, textTransform: 'uppercase', color: 'var(--pen3)' }}>
                Pastas
              </span>
              <button
                onClick={() => setCreatingFolder(true)}
                title="Nova pasta"
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', padding: '1px 3px', borderRadius: 4, display: 'flex', alignItems: 'center' }}
              >
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                  <path d="M8 3 V13 M3 8 H13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            {creatingFolder && (
              <div style={{ padding: '4px 10px 8px', display: 'flex', gap: 6, alignItems: 'center' }}>
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, color: 'var(--pen3)' }}>
                  <path d="M2 4h5l1.5 2H14v7H2V4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
                </svg>
                <input
                  ref={newFolderInputRef}
                  value={newFolderName}
                  onChange={e => setNewFolderName(e.target.value)}
                  onBlur={submitNewFolder}
                  onKeyDown={e => {
                    if (e.key === 'Enter') submitNewFolder();
                    if (e.key === 'Escape') { setNewFolderName(''); setCreatingFolder(false); }
                  }}
                  placeholder="Nome da pasta"
                  style={{
                    flex: 1, fontSize: 12, border: '1px solid var(--line)', borderRadius: 5,
                    padding: '3px 7px', outline: 'none', background: '#fff',
                  }}
                />
              </div>
            )}

            {folders.map(folder => (
              <FolderRow
                key={folder.id}
                folder={folder}
                conversations={convsByFolder[folder.id] ?? []}
                activeId={activeId}
                allFolders={folders}
                onSelect={id => closeAfter(() => onSelect(id))()}
                onMove={(convId, fId) => moveConvMutation.mutate({ convId, folderId: fId })}
                onRename={(id, name) => renameFolderMutation.mutate({ id, name })}
                onDelete={id => deleteFolderMutation.mutate(id)}
              />
            ))}
          </div>
        )}

        {/* Botão criar primeira pasta */}
        {folders.length === 0 && !creatingFolder && (
          <div style={{ padding: '0 10px 10px' }}>
            <button
              onClick={() => setCreatingFolder(true)}
              style={{
                width: '100%', background: 'none', border: '1px dashed var(--line2)',
                borderRadius: 7, padding: '6px 10px', fontSize: 11.5,
                color: 'var(--pen3)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                <path d="M2 4h5l1.5 2H14v7H2V4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
                <path d="M8 8 V12 M6 10 H10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
              Nova pasta
            </button>
          </div>
        )}

        {/* Grupos por data */}
        {groups.length === 0 && folders.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 80 }}>
            <p style={{ fontSize: 12, color: 'var(--pen3)', textAlign: 'center', padding: '0 16px' }}>
              Nenhuma consulta anterior
            </p>
          </div>
        ) : (
          groups.map(group => (
            <div key={group.label} style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.2, textTransform: 'uppercase', color: 'var(--pen3)', padding: '6px 10px' }}>
                {group.label}
              </div>
              {group.items.map(conv => (
                <ConvItem
                  key={conv.id}
                  conv={conv}
                  activeId={activeId}
                  folders={folders}
                  onSelect={closeAfter(() => onSelect(conv.id))}
                  onMove={fId => moveConvMutation.mutate({ convId: conv.id, folderId: fId })}
                />
              ))}
            </div>
          ))
        )}
      </div>

      {/* Limite semanal */}
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
                    <span style={{ fontSize: 10, color: 'var(--pen3)', fontWeight: 600, letterSpacing: 0.5 }}>LIMITE SEMANAL</span>
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

      {/* Footer usuário */}
      <div ref={userMenuRef} style={{ borderTop: '1px solid var(--line2)', padding: '12px 14px', position: 'relative' }}>
        {userMenuOpen && (
          <div style={{
            position: 'absolute', bottom: 'calc(100% + 4px)', left: 14, right: 14,
            background: 'var(--paper)', border: '1px solid var(--line2)',
            borderRadius: 10, boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            overflow: 'hidden', zIndex: 300,
          }}>
            <button onClick={() => { setUserMenuOpen(false); setShowProfile(true); }} style={menuItemStyle}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="6" r="3" stroke="currentColor" strokeWidth="1.4" />
                <path d="M2 14c0-2.5 2.7-4 6-4s6 1.5 6 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
              Editar perfil
            </button>
            <div style={{ height: 1, background: 'var(--line2)', margin: '0 10px' }} />
            <button onClick={logout} style={{ ...menuItemStyle, color: '#ef4444' }}>
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
          onClick={() => setUserMenuOpen(o => !o)}
          style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', borderRadius: 8, padding: '2px 4px', transition: 'background 0.1s' }}
          onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--fill)'}
          onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
        >
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--mint)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 600, color: 'var(--pen2)', flexShrink: 0 }}>
            {user?.initial ?? '?'}
          </div>
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
      <div onClick={onToggle} style={{ position: 'fixed', inset: 0, zIndex: 199, background: 'rgba(0,0,0,0.35)' }} />
      {aside}
    </>
  );
}

export const Sidebar = memo(SidebarComponent);

const menuItemStyle: React.CSSProperties = {
  width: '100%', display: 'flex', alignItems: 'center', gap: 9,
  padding: '10px 14px', background: 'none', border: 'none',
  fontSize: 13, color: 'var(--ink)', cursor: 'pointer', textAlign: 'left',
};
