import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { useCurrentUser } from '../lib/useCurrentUser';
import { useUserUsage } from '../lib/useUserUsage';
import { listConversations, type ConversationSummary } from '../api/conversations';
import { listFolders, createFolder, renameFolder, deleteFolder, moveConversation, bulkMoveConversations, type Folder } from '../api/folders';
import { logout } from '../lib/auth';
import { ProfileModal } from './ProfileModal';
import { useIsMobile } from '../hooks/useIsMobile';
import { ConvItem } from './sidebar/ConvItem';
import { FolderRow } from './sidebar/FolderRow';
import { DropZoneNoPasta } from './sidebar/DropZoneNoPasta';
import { groupByDate } from './sidebar/groupByDate';
import { ctxItemStyle, menuItemStyle } from './sidebar/styles';

export const SIDEBAR_PINNED_KEY = 'm360_sidebar_pinned';

/** Largura do trilho colapsado, em px. */
const RAIL_WIDTH = 56;

interface Props {
  activeId?: string;
  onNew: (folderId?: string, folderName?: string) => void;
  onSelect: (id: string) => void;
  open: boolean;
  onToggle: () => void;
  usageTick?: number;
}

// ── Sidebar principal ────────────────────────────────────────────

function SidebarComponent({ activeId, onNew, onSelect, open, onToggle, usageTick = 0 }: Props) {
  const isMobile = useIsMobile();
  const user = useCurrentUser();
  const usage = useUserUsage(usageTick);
  const queryClient = useQueryClient();

  const { data: todasConversas = [] } = useQuery<ConversationSummary[]>({
    queryKey: ['conversations'],
    queryFn: listConversations,
    staleTime: 60_000,
  });

  // Conversas antigas do Agregador saem da lista junto com o modo. Sem este
  // filtro elas continuariam abríveis, e abrir uma delas levaria a uma tela
  // que não existe mais. O dado permanece no banco — isto é só a vista.
  const conversations = useMemo(
    () => todasConversas.filter(c => c.feature !== 'AGREGADOR'),
    [todasConversas],
  );

  const { data: folders = [] } = useQuery<Folder[]>({
    queryKey: ['folders'],
    queryFn: listFolders,
    staleTime: 60_000,
  });

  const createFolderMutation = useMutation({
    mutationFn: (name: string) => createFolder(name),
    onMutate: async (name: string) => {
      await queryClient.cancelQueries({ queryKey: ['folders'] });
      const previous = queryClient.getQueryData<Folder[]>(['folders']);
      const optimistic: Folder = {
        id: `optimistic-${Date.now()}`,
        name,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      queryClient.setQueryData<Folder[]>(['folders'], (old = []) => [...old, optimistic]);
      return { previous };
    },
    onError: (_err, _name, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['folders'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['folders'] }),
  });

  const renameFolderMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameFolder(id, name),
    onMutate: async ({ id, name }) => {
      await queryClient.cancelQueries({ queryKey: ['folders'] });
      const previous = queryClient.getQueryData<Folder[]>(['folders']);
      queryClient.setQueryData<Folder[]>(['folders'], (old = []) =>
        old.map(f => f.id === id ? { ...f, name } : f)
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['folders'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['folders'] }),
  });

  const deleteFolderMutation = useMutation({
    mutationFn: (id: string) => deleteFolder(id),
    onMutate: async (id: string) => {
      await queryClient.cancelQueries({ queryKey: ['folders'] });
      await queryClient.cancelQueries({ queryKey: ['conversations'] });
      const previousFolders = queryClient.getQueryData<Folder[]>(['folders']);
      const previousConvs = queryClient.getQueryData<ConversationSummary[]>(['conversations']);
      queryClient.setQueryData<Folder[]>(['folders'], (old = []) => old.filter(f => f.id !== id));
      queryClient.setQueryData<ConversationSummary[]>(['conversations'], (old = []) =>
        old.map(c => c.folder_id === id ? { ...c, folder_id: null } : c)
      );
      return { previousFolders, previousConvs };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previousFolders) queryClient.setQueryData(['folders'], ctx.previousFolders);
      if (ctx?.previousConvs) queryClient.setQueryData(['conversations'], ctx.previousConvs);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['folders'] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });

  const moveConvMutation = useMutation({
    mutationFn: ({ convId, folderId }: { convId: string; folderId: string | null }) =>
      moveConversation(convId, folderId),
    onMutate: async ({ convId, folderId }) => {
      await queryClient.cancelQueries({ queryKey: ['conversations'] });
      const previous = queryClient.getQueryData<ConversationSummary[]>(['conversations']);
      queryClient.setQueryData<ConversationSummary[]>(['conversations'], (old = []) =>
        old.map(c => c.id === convId ? { ...c, folder_id: folderId } : c)
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['conversations'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  });

  // `pinned` é a preferência persistida (fixada por clique); `hovering` é
  // efêmero. A barra abre quando qualquer um dos dois é verdadeiro.
  //
  // Chave nova, e não a antiga 'sidebarCollapsed': o valor '1' significava
  // COLAPSADA e agora significaria FIXADA ABERTA — o oposto. Reaproveitá-la
  // entregaria a cada usuário existente exatamente o contrário do que ele
  // tinha. Com chave nova todo mundo começa colapsado, que é o pedido.
  const [pinned, setPinned] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_PINNED_KEY) === '1'; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem(SIDEBAR_PINNED_KEY, pinned ? '1' : '0'); } catch { /* ignore */ }
  }, [pinned]);
  const [hovering, setHovering] = useState(false);

  const [showUsageTip, setShowUsageTip] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [selectedConvIds, setSelectedConvIds] = useState<Set<string>>(new Set());
  const [draggingConvId, setDraggingConvId] = useState<string | null>(null);
  const [showBulkFolderPicker, setShowBulkFolderPicker] = useState(false);
  const newFolderInputRef = useRef<HTMLInputElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const selectionMode = selectedConvIds.size > 0;

  const bulkMoveMutation = useMutation({
    mutationFn: ({ ids, folderId }: { ids: string[]; folderId: string | null }) =>
      bulkMoveConversations(ids, folderId),
    onMutate: async ({ ids, folderId }) => {
      await queryClient.cancelQueries({ queryKey: ['conversations'] });
      const previous = queryClient.getQueryData<ConversationSummary[]>(['conversations']);
      const idSet = new Set(ids);
      queryClient.setQueryData<ConversationSummary[]>(['conversations'], (old = []) =>
        old.map(c => idSet.has(c.id) ? { ...c, folder_id: folderId } : c)
      );
      setSelectedConvIds(new Set());
      setShowBulkFolderPicker(false);
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['conversations'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  });

  const toggleSelect = useCallback((convId: string) => {
    setSelectedConvIds(prev => {
      const next = new Set(prev);
      if (next.has(convId)) next.delete(convId); else next.add(convId);
      return next;
    });
  }, []);

  const handleDrop = useCallback((folderId: string | null) => {
    if (!draggingConvId) return;
    if (selectedConvIds.has(draggingConvId) && selectedConvIds.size > 1) {
      bulkMoveMutation.mutate({ ids: [...selectedConvIds], folderId });
    } else {
      moveConvMutation.mutate({ convId: draggingConvId, folderId });
    }
    setDraggingConvId(null);
  }, [draggingConvId, selectedConvIds, bulkMoveMutation.mutate, moveConvMutation.mutate]);

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

  // Handlers com referência estável — os itens da lista são memoizados e
  // qualquer arrow inline aqui anularia o memo a cada render do Sidebar.
  const handleSelectConv = useCallback(
    (id: string) => closeAfter(() => onSelect(id))(),
    [closeAfter, onSelect],
  );
  const handleMoveConv = useCallback(
    (convId: string, folderId: string | null) => moveConvMutation.mutate({ convId, folderId }),
    [moveConvMutation.mutate],
  );
  const handleRenameFolder = useCallback(
    (id: string, name: string) => renameFolderMutation.mutate({ id, name }),
    [renameFolderMutation.mutate],
  );
  const handleDeleteFolder = useCallback(
    (id: string) => deleteFolderMutation.mutate(id),
    [deleteFolderMutation.mutate],
  );
  const handleNewInFolder = useCallback(
    (folderId: string, folderName: string) => closeAfter(() => onNew(folderId, folderName))(),
    [closeAfter, onNew],
  );
  const handleDragStart = useCallback((convId: string) => setDraggingConvId(convId), []);

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

  const rail = (
      <aside data-testid="sidebar-rail" style={{
        width: RAIL_WIDTH, flexShrink: 0, height: '100%',
        borderRight: '1px solid var(--line2)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        background: '#fbfdf7', padding: '14px 0',
      }}>
        <button
          onClick={() => setPinned(true)}
          title="Fixar barra lateral aberta"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', padding: 6, borderRadius: 6, display: 'flex', alignItems: 'center', marginBottom: 14 }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M6 3 L11 8 L6 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <button
          onClick={() => onNew()}
          title="Nova consulta"
          style={{
            width: 32, height: 32, borderRadius: 8, background: 'var(--ink)', color: '#fff',
            border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, marginBottom: 'auto',
          }}
        >
          +
        </button>
        <div
          onClick={() => setUserMenuOpen(o => !o)}
          title={user?.name ?? ''}
          style={{
            width: 32, height: 32, borderRadius: '50%', background: 'var(--mint)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 600, color: 'var(--pen2)', cursor: 'pointer', position: 'relative',
          }}
          ref={userMenuRef}
        >
          {user?.initial ?? '?'}
          {userMenuOpen && (
            <div style={{
              position: 'absolute', bottom: 0, left: 'calc(100% + 8px)',
              background: 'var(--paper)', border: '1px solid var(--line2)',
              borderRadius: 10, boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
              overflow: 'hidden', zIndex: 300, width: 170,
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
        </div>
        {showProfile && (
          <ProfileModal
            onClose={() => setShowProfile(false)}
            onSuccess={() => queryClient.invalidateQueries({ queryKey: ['currentUser'] })}
          />
        )}
      </aside>
  );

  const aside = (
    <aside data-testid="sidebar-panel" style={{
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
      {!isMobile && (
        <div style={{ padding: '10px 10px 0', display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={() => { setPinned(false); setHovering(false); }}
            title="Recolher barra lateral"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', padding: 4, borderRadius: 6, display: 'flex', alignItems: 'center' }}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M10 3 L5 8 L10 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      )}
      {isMobile && (
        <div style={{ padding: '14px 14px 0', display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={onToggle} style={{ background: 'none', border: 'none', color: 'var(--pen3)', cursor: 'pointer', padding: 4, display: 'flex', alignItems: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      )}

      <div style={{ padding: '18px 14px 10px' }}>
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
                onSelect={handleSelectConv}
                onMove={handleMoveConv}
                onRename={handleRenameFolder}
                onDelete={handleDeleteFolder}
                onNewInFolder={handleNewInFolder}
                selectedConvIds={selectedConvIds}
                selectionMode={selectionMode}
                onToggleSelect={toggleSelect}
                onDragStart={handleDragStart}
                onDropConv={handleDrop}
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

        {/* Zona de drop "Sem pasta" — visível apenas durante drag de conversa de dentro de uma pasta */}
        {draggingConvId && (
          <DropZoneNoPasta onDrop={() => handleDrop(null)} />
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
                  onSelect={handleSelectConv}
                  onMove={handleMoveConv}
                  selected={selectedConvIds.has(conv.id)}
                  selectionMode={selectionMode}
                  onToggleSelect={toggleSelect}
                  onDragStart={handleDragStart}
                />
              ))}
            </div>
          ))
        )}
      </div>

      {/* Barra de seleção múltipla */}
      {selectionMode && (
        <div style={{ padding: '8px 12px', borderTop: '1px solid var(--line2)', background: 'var(--fill)', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--ink)' }}>{selectedConvIds.size} selecionada{selectedConvIds.size > 1 ? 's' : ''}</span>
            <button onClick={() => setSelectedConvIds(new Set())} style={{ background: 'none', border: 'none', fontSize: 11, color: 'var(--pen3)', cursor: 'pointer' }}>Limpar</button>
          </div>
          {showBulkFolderPicker ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <button onClick={() => { bulkMoveMutation.mutate({ ids: [...selectedConvIds], folderId: null }); setShowBulkFolderPicker(false); }}
                style={{ ...ctxItemStyle, fontSize: 11.5, padding: '5px 8px', color: 'var(--pen2)' }}>
                Sem pasta
              </button>
              {folders.map(f => (
                <button key={f.id} onClick={() => bulkMoveMutation.mutate({ ids: [...selectedConvIds], folderId: f.id })}
                  style={{ ...ctxItemStyle, fontSize: 11.5, padding: '5px 8px' }}>
                  {f.name}
                </button>
              ))}
              <button onClick={() => setShowBulkFolderPicker(false)} style={{ ...ctxItemStyle, fontSize: 11, padding: '4px 8px', color: 'var(--pen3)' }}>Cancelar</button>
            </div>
          ) : (
            <button
              onClick={() => setShowBulkFolderPicker(true)}
              style={{ width: '100%', padding: '6px 0', borderRadius: 7, border: 'none', background: 'var(--ink)', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
            >
              Mover {selectedConvIds.size} conversa{selectedConvIds.size > 1 ? 's' : ''}
            </button>
          )}
        </div>
      )}

      {/* Limite semanal */}
      {usage.hasLimit && !usage.loading && (
        <div style={{ padding: '10px 14px 2px' }}>
          {(() => {
            const pct = usage.usagePercentage ?? 0;
            const barColor = pct >= 80 ? '#f87171' : pct >= 50 ? '#facc15' : '#4ade80';
            // Valor puramente informativo ("faltam N dias"), recalculado a cada
            // render do Sidebar. A regra quer funcao pura no render; mover isto
            // para estado exigiria um timer so para atualizar um contador de
            // DIAS, o que nao se paga.
            // eslint-disable-next-line react-hooks/purity
            const agora = Date.now();
            const daysLeft = usage.weekResetAt
              ? Math.max(0, Math.ceil((usage.weekResetAt.getTime() - agora) / 86400000))
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
          onSuccess={() => queryClient.invalidateQueries({ queryKey: ['currentUser'] })}
        />
      )}
    </aside>
  );

  if (isMobile) {
    return (
      <>
        <div onClick={onToggle} style={{ position: 'fixed', inset: 0, zIndex: 199, background: 'rgba(0,0,0,0.35)' }} />
        {aside}
      </>
    );
  }

  // Fixada por clique: ocupa espaço no fluxo e o hover não a fecha.
  if (pinned) return aside;

  // Não fixada: o trilho fica no fluxo e o painel aparece SOBREPOSTO no hover.
  // Sobrepor em vez de empurrar é deliberado — com push, o chat inteiro se
  // desloca toda vez que o mouse encosta na borda esquerda da tela.
  return (
    <div
      style={{ position: 'relative', width: RAIL_WIDTH, flexShrink: 0, height: '100%' }}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      {rail}
      {hovering && (
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, zIndex: 150,
          boxShadow: '2px 0 20px rgba(0,0,0,0.12)',
        }}>
          {aside}
        </div>
      )}
    </div>
  );
}

export const Sidebar = memo(SidebarComponent);
