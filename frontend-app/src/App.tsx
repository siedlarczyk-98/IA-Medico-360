import { lazy, Suspense, useCallback, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
// moveConversation is still used by Sidebar; not needed here after folder_id in request
import { Navigate, Route, Routes } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { Topbar } from './components/Topbar';
import { EmptyState } from './components/EmptyState';
import { ChatView } from './components/ChatView';
import { InputBar } from './components/InputBar';
import { ClarificationPrompt } from './components/ClarificationPrompt';
import { ModelSelector } from './components/ModelSelector';
import { EmptyStateAgregador } from './components/EmptyStateAgregador';
import type { Effort, OrchestratorMode } from './components/InputBar';
import { streamQuery, queryOrquestrador, type Message } from './api/orquestrador';
import { streamAgregador } from './api/agregador';
import { isAuthenticated, isTokenExpired } from './lib/auth';
import { useCurrentUser } from './lib/useCurrentUser';
import { getConversation } from './api/conversations';

// Páginas de auth são carregadas sob demanda (não fazem parte da rota principal).
const LoginPage = lazy(() => import('./pages/LoginPage').then(m => ({ default: m.LoginPage })));
const InvitePage = lazy(() => import('./pages/InvitePage').then(m => ({ default: m.InvitePage })));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage').then(m => ({ default: m.OnboardingPage })));
const RegisterPage = lazy(() => import('./pages/RegisterPage').then(m => ({ default: m.RegisterPage })));
const EmbedAuthPage = lazy(() => import('./pages/EmbedAuthPage').then(m => ({ default: m.EmbedAuthPage })));

type AppMode = 'orquestrador' | 'agregador';

const BACKEND_TO_CHIP: Record<string, string> = {
  QUICK_SEARCH:      'busca',
  CLINICAL_REASONING:'raciocinio',
  PHARMA_CHECK:      'farmaco',
  PHARMA_BULA:       'farmaco',
  PHARMA_RECEITA:    'farmaco',
  PHARMA_GENERICO:   'farmaco',
  PRODUCTIVITY:      'produtividade',
};

interface PendingClarification {
  conversationId: string;
  questions: string[];
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated() || isTokenExpired()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function MainApp() {
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [mode, setMode] = useState<AppMode>('orquestrador');
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | undefined>();
  const [clarification, setClarification] = useState<PendingClarification | null>(null);
  const [selectedMode, setSelectedMode] = useState<OrchestratorMode>('QUICK_SEARCH');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [scrollTrigger, setScrollTrigger] = useState(0);
  const [usageTick, setUsageTick] = useState(0);
  const pendingFolderIdRef = useRef<string | undefined>(undefined);
  const pendingFolderNameRef = useRef<string | undefined>(undefined);
  const [pendingFolderName, setPendingFolderName] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);
  // Tracks the index of the assistant message being streamed, so we can remove it if the stream is aborted mid-way
  const streamMsgIndexRef = useRef<number>(-1);
  // Stable ref to latest messages — avoids recreating sendMessage on every token
  const messagesRef = useRef<Message[]>(messages);
  messagesRef.current = messages;
  // Flush em lote dos tokens de streaming: acumulamos em refs e aplicamos ao
  // state uma vez por frame (requestAnimationFrame), evitando re-render por token.
  const rafRef = useRef<number | null>(null);

  const cancelFlush = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const scheduleFlush = useCallback((flush: () => void) => {
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      flush();
    });
  }, []);

  const topbarTitle = useMemo(() =>
    messages.length === 0
      ? 'Nova consulta'
      : (messages.find(m => m.role === 'user')?.content.slice(0, 60) ?? '') + '…',
    [messages]
  );

  const runOrquestrador = useCallback(async (params: Parameters<typeof streamQuery>[0] & { effort?: Effort; priorMessages?: Message[] }) => {
    abortRef.current?.abort();
    cancelFlush();

    // Remove partial assistant message left by an aborted previous stream
    const prevStreamIdx = streamMsgIndexRef.current;
    if (prevStreamIdx !== -1) {
      setMessages(prev => prev.slice(0, prevStreamIdx));
      streamMsgIndexRef.current = -1;
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    setClarification(null);

    const acc = { current: '' };
    let assistantIndex = -1;

    const flushAssistant = () => {
      if (assistantIndex === -1) return;
      setMessages(prev => {
        if (assistantIndex >= prev.length) return prev;
        const next = [...prev];
        next[assistantIndex] = { ...next[assistantIndex], content: acc.current };
        return next;
      });
    };

    const history = (params.priorMessages ?? []).map(m => ({ role: m.role, content: m.content }));
    const folder_id = pendingFolderIdRef.current;

    try {
      for await (const event of streamQuery({ ...params, history, folder_id }, ctrl.signal)) {
        if (event.type === 'clarification') {
          const formatted = event.questions.map((q, i) => `${i + 1}. ${q}`).join('\n');
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `Para responder com mais precisão, preciso de algumas informações:\n\n${formatted}`,
          }]);
          setClarification({ conversationId: event.conversation_id, questions: event.questions });
          return;
        }
        if (event.type === 'cache_hit') {
          setActiveConvId(event.conversation_id);
          pendingFolderIdRef.current = undefined;
          setPendingFolderName(undefined);
          queryClient.invalidateQueries({ queryKey: ['conversations'] });
          const chipMode = BACKEND_TO_CHIP[event.mode] ?? event.mode;
          setMessages(prev => [...prev, { role: 'assistant', content: event.response_text, mode: chipMode }]);
          return;
        }
        if (event.type === 'token') {
          acc.current += event.text;
          if (assistantIndex === -1) {
            setMessages(prev => {
              assistantIndex = prev.length;
              streamMsgIndexRef.current = prev.length;
              return [...prev, { role: 'assistant', content: acc.current }];
            });
          } else {
            scheduleFlush(flushAssistant);
          }
        }
        if (event.type === 'done') {
          setActiveConvId(event.conversation_id);
          pendingFolderIdRef.current = undefined;
          setPendingFolderName(undefined);
          queryClient.invalidateQueries({ queryKey: ['conversations'] });
          const chipMode = BACKEND_TO_CHIP[event.mode] ?? event.mode;
          if (assistantIndex !== -1) {
            setMessages(prev => {
              if (assistantIndex >= prev.length) return prev;
              const next = [...prev];
              next[assistantIndex] = {
                ...next[assistantIndex],
                mode: chipMode,
                ...(event.citations && event.citations.length > 0 ? { citations: event.citations } : {}),
              };
              return next;
            });
          }
        }
        if (event.type === 'error') {
          if (event.status === 'unsupported_mode') {
            // Modos PharmaDB não suportam streaming — fallback para /query
            const result = await queryOrquestrador({ ...params, folder_id });
            const chipMode = BACKEND_TO_CHIP[result.mode] ?? result.mode;
            setMessages(prev => [...prev, { role: 'assistant', content: result.response, mode: chipMode }]);
            if (result.conversation_id) {
              setActiveConvId(result.conversation_id);
              pendingFolderIdRef.current = undefined;
              setPendingFolderName(undefined);
              queryClient.invalidateQueries({ queryKey: ['conversations'] });
            }
          } else {
            setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${event.message}` }]);
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Erro ao conectar com o servidor.' }]);
    } finally {
      cancelFlush();
      flushAssistant();
      streamMsgIndexRef.current = -1;
      setStreaming(false);
      setUsageTick(t => t + 1);
    }
  }, [cancelFlush, scheduleFlush]);

  const runAgregador = useCallback(async (prompt: string, priorMessages: Message[], effort: Effort = 'detalhado') => {
    if (selectedModels.length === 0) return;
    abortRef.current?.abort();
    cancelFlush();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);

    // Uma mensagem por modelo, identificada pelo model_id
    const buffers: Record<string, string> = {};
    // baseIndex garante que buscamos/atualizamos apenas mensagens desta sessão de streaming,
    // evitando sobrescrever respostas de perguntas anteriores com o mesmo model_id
    let baseIndex = -1;
    // Conjunto de model_ids já materializados como mensagem (criação é síncrona;
    // atualizações subsequentes são agrupadas via requestAnimationFrame).
    const created = new Set<string>();

    const flushBuffers = () => {
      setMessages(prev => {
        const next = [...prev];
        for (const mid of created) {
          const idx = next.findIndex((m, i) => i >= baseIndex && m.role === 'assistant' && m.mode === mid);
          if (idx !== -1) next[idx] = { ...next[idx], content: buffers[mid] };
        }
        return next;
      });
    };

    const folderIdForStream = pendingFolderIdRef.current;

    try {
      const history = priorMessages.map(m => ({ role: m.role, content: m.content }));
      for await (const event of streamAgregador(prompt, selectedModels, ctrl.signal, activeConvId, history, effort, folderIdForStream)) {
        if (event.type === 'delta') {
          const mid = event.model_id;
          buffers[mid] = (buffers[mid] ?? '') + event.delta;
          if (!created.has(mid)) {
            created.add(mid);
            setMessages(prev => {
              if (baseIndex === -1) baseIndex = prev.length;
              return [...prev, { role: 'assistant', content: buffers[mid], mode: mid }];
            });
          } else {
            scheduleFlush(flushBuffers);
          }
        }
        if (event.type === 'complete') {
          if (event.citations && event.citations.length > 0) {
            const mid = event.model_id;
            setMessages(prev => {
              const next = [...prev];
              const idx = next.findIndex((m, i) => i >= baseIndex && m.role === 'assistant' && m.mode === mid);
              if (idx !== -1) next[idx] = { ...next[idx], citations: event.citations };
              return next;
            });
          }
        }
        if (event.type === 'pubmed') {
          const mid = event.model_id;
          setMessages(prev => {
            const next = [...prev];
            const idx = next.findIndex((m, i) => i >= baseIndex && m.role === 'assistant' && m.mode === mid);
            if (idx !== -1) next[idx] = { ...next[idx], pubmed_validation: { cited_verified: event.cited_verified, newer_guidelines: event.newer_guidelines } };
            return next;
          });
        }
        if (event.type === 'done') {
          setActiveConvId(event.conversation_id);
          pendingFolderIdRef.current = undefined;
          setPendingFolderName(undefined);
          queryClient.invalidateQueries({ queryKey: ['conversations'] });
        }
        if (event.type === 'error') {
          const errMsg = event.error || 'Tempo limite excedido ou erro no modelo. Tente novamente.';
          setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${errMsg}` }]);
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Erro ao conectar com o servidor.' }]);
    } finally {
      cancelFlush();
      flushBuffers();
      setStreaming(false);
      setUsageTick(t => t + 1);
    }
  }, [selectedModels, activeConvId, cancelFlush, scheduleFlush]);

  const sendMessage = useCallback((text: string, effort: Effort = 'detalhado') => {
    const priorMessages = messagesRef.current;
    if (mode === 'orquestrador') {
      runOrquestrador({ prompt: text, conversation_id: activeConvId, effort, mode: selectedMode, priorMessages });
    } else {
      runAgregador(text, priorMessages, effort);
    }
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setScrollTrigger(n => n + 1);
  }, [mode, activeConvId, selectedMode, runOrquestrador, runAgregador]);

  const sendClarification = useCallback((answers: string) => {
    if (!clarification) return;
    setMessages(prev => [...prev, { role: 'user', content: answers }]);
    runOrquestrador({
      prompt: answers,
      conversation_id: clarification.conversationId,
      clarification_answers: answers,
    });
  }, [clarification, runOrquestrador]);

  const handleNew = useCallback((folderId?: string, folderName?: string) => {
    abortRef.current?.abort();
    setMessages([]);
    setStreaming(false);
    setActiveConvId(undefined);
    setClarification(null);
    setSelectedMode('QUICK_SEARCH');
    pendingFolderIdRef.current = folderId;
    pendingFolderNameRef.current = folderName;
    setPendingFolderName(folderName);
  }, []);

  const handleSelectConversation = useCallback(async (id: string) => {
    abortRef.current?.abort();
    setStreaming(false);
    setClarification(null);
    pendingFolderIdRef.current = undefined;
    setPendingFolderName(undefined);
    try {
      const detail = await getConversation(id);
      setMessages(detail.messages);
      setActiveConvId(detail.id);
      const isAgregador = detail.feature === 'AGREGADOR';
      setMode(isAgregador ? 'agregador' : 'orquestrador');
      if (isAgregador) {
        const models = [...new Set(
          detail.messages
            .filter(m => m.role === 'assistant' && m.mode)
            .map(m => m.mode as string)
        )];
        setSelectedModels(models.length > 0 ? models : selectedModels);
      }
    } catch {
      handleNew();
    }
  }, [handleNew, selectedModels]);

  const handleModeChange = useCallback((m: AppMode) => {
    setMode(m);
    handleNew();
  }, [handleNew]);

  const showClarification = clarification && !streaming;
  const agregadorBlocked = mode === 'agregador' && selectedModels.length === 0;

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar activeId={activeConvId} onNew={handleNew} onSelect={handleSelectConversation} open={sidebarOpen} onToggle={() => setSidebarOpen(o => !o)} usageTick={usageTick} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Topbar title={topbarTitle} mode={mode} onModeChange={handleModeChange} onMenuToggle={() => setSidebarOpen(o => !o)} />
        {pendingFolderName && messages.length === 0 && (
          <div style={{ padding: '6px 20px', background: 'var(--fill2)', borderBottom: '1px solid var(--line2)', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--pen2)' }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path d="M2 4h5l1.5 2H14v7H2V4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            Nova consulta em <strong style={{ color: 'var(--ink)' }}>{pendingFolderName}</strong>
          </div>
        )}

        {mode === 'agregador' && messages.length > 0 && (
          <ModelSelector selected={selectedModels} onChange={setSelectedModels} max={1} locked />
        )}

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {messages.length === 0 && !streaming ? (
            mode === 'agregador' ? (
              <>
                <EmptyStateAgregador selected={selectedModels} onChange={setSelectedModels} />
                <InputBar onSend={sendMessage} disabled={streaming || agregadorBlocked}
                  placeholder={agregadorBlocked ? 'Selecione um modelo acima para começar.' : undefined} />
              </>
            ) : (
              <>
                <EmptyState userName={currentUser?.firstName} onModeSelect={setSelectedMode} selectedMode={selectedMode} />
                <InputBar onSend={sendMessage} disabled={streaming} mode={selectedMode} onModeChange={setSelectedMode} />
              </>
            )
          ) : (
            <>
              <ChatView messages={messages} streaming={streaming} streamingMode={mode === 'orquestrador' ? selectedMode : undefined} scrollToBottomTrigger={scrollTrigger} />
              {showClarification
                ? <ClarificationPrompt onSend={sendClarification} />
                : <InputBar onSend={sendMessage} disabled={streaming || agregadorBlocked} mode={mode === 'orquestrador' ? selectedMode : undefined} onModeChange={mode === 'orquestrador' ? setSelectedMode : undefined} />
              }
            </>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/cadastro" element={<RegisterPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/invite" element={<InvitePage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/embed-auth" element={<EmbedAuthPage />} />
        <Route path="/" element={
          <RequireAuth>
            <MainApp />
          </RequireAuth>
        } />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
