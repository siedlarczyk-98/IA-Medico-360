import { useCallback, useRef, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { Topbar } from './components/Topbar';
import { EmptyState } from './components/EmptyState';
import { ChatView } from './components/ChatView';
import { InputBar } from './components/InputBar';
import { ClarificationPrompt } from './components/ClarificationPrompt';
import { ModelSelector } from './components/ModelSelector';
import { EmptyStateAgregador } from './components/EmptyStateAgregador';
import type { Effort } from './components/InputBar';
import { streamQuery, queryOrquestrador, type Message } from './api/orquestrador';
import { streamAgregador } from './api/agregador';
import { isAuthenticated, isTokenExpired } from './lib/auth';
import { useCurrentUser } from './lib/useCurrentUser';
import { getConversation } from './api/conversations';
import { LoginPage } from './pages/LoginPage';
import { InvitePage } from './pages/InvitePage';
import { OnboardingPage } from './pages/OnboardingPage';
import { RegisterPage } from './pages/RegisterPage';

type AppMode = 'orquestrador' | 'agregador';

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
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [mode, setMode] = useState<AppMode>('orquestrador');
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | undefined>();
  const [clarification, setClarification] = useState<PendingClarification | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [scrollTrigger, setScrollTrigger] = useState(0);
  const [usageTick, setUsageTick] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const topbarTitle = messages.length === 0
    ? 'Nova consulta'
    : (messages.find(m => m.role === 'user')?.content.slice(0, 60) ?? '') + '…';

  function appendAssistant(token: string, accumulated: { current: string }, added: { current: boolean }) {
    accumulated.current += token;
    if (!added.current) {
      setMessages(prev => [...prev, { role: 'assistant', content: accumulated.current }]);
      added.current = true;
    } else {
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: accumulated.current };
        return next;
      });
    }
  }

  const runOrquestrador = useCallback(async (params: Parameters<typeof streamQuery>[0] & { effort?: Effort }) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    setClarification(null);

    const acc = { current: '' };
    const added = { current: false };

    try {
      for await (const event of streamQuery(params, ctrl.signal)) {
        if (event.type === 'clarification') {
          const formatted = event.questions.map((q, i) => `${i + 1}. ${q}`).join('\n');
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `Para responder com mais precisão, preciso de algumas informações:\n\n${formatted}`,
          }]);
          setClarification({ conversationId: event.conversation_id, questions: event.questions });
          return;
        }
        if (event.type === 'token')  appendAssistant(event.text, acc, added);
        if (event.type === 'done')  setActiveConvId(event.conversation_id);
        if (event.type === 'error') {
          if (event.status === 'unsupported_mode') {
            // PHARMA_CHECK não suporta streaming — fallback para /query
            const result = await queryOrquestrador(params);
            setMessages(prev => [...prev, { role: 'assistant', content: result.response, mode: result.mode }]);
            if (result.conversation_id) setActiveConvId(result.conversation_id);
          } else {
            setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${event.message}` }]);
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Erro ao conectar com o servidor.' }]);
    } finally {
      setStreaming(false);
      setUsageTick(t => t + 1);
    }
  }, []);

  const runAgregador = useCallback(async (prompt: string, priorMessages: Message[], effort: Effort = 'detalhado') => {
    if (selectedModels.length === 0) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);

    // Uma mensagem por modelo, identificada pelo model_id
    const buffers: Record<string, string> = {};
    // baseIndex garante que buscamos/atualizamos apenas mensagens desta sessão de streaming,
    // evitando sobrescrever respostas de perguntas anteriores com o mesmo model_id
    let baseIndex = -1;

    try {
      const history = priorMessages.map(m => ({ role: m.role, content: m.content }));
      for await (const event of streamAgregador(prompt, selectedModels, ctrl.signal, activeConvId, history, effort)) {
        if (event.type === 'delta') {
          const mid = event.model_id;
          buffers[mid] = (buffers[mid] ?? '') + event.delta;
          setMessages(prev => {
            if (baseIndex === -1) baseIndex = prev.length;
            const next = [...prev];
            const idx = next.findIndex((m, i) => i >= baseIndex && m.role === 'assistant' && m.mode === mid);
            if (idx === -1) {
              next.push({ role: 'assistant', content: buffers[mid], mode: mid });
            } else {
              next[idx] = { ...next[idx], content: buffers[mid] };
            }
            return next;
          });
        }
        if (event.type === 'done') setActiveConvId(event.conversation_id);
        if (event.type === 'error') {
          setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${event.error ?? 'Erro no modelo'}` }]);
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Erro ao conectar com o servidor.' }]);
    } finally {
      setStreaming(false);
      setUsageTick(t => t + 1);
    }
  }, [selectedModels, activeConvId]);

  const sendMessage = useCallback((text: string, effort: Effort = 'detalhado') => {
    // Capturar histórico ANTES de adicionar a nova mensagem do usuário
    setMessages(prev => {
      const priorMessages = prev;
      if (mode === 'orquestrador') {
        runOrquestrador({ prompt: text, conversation_id: activeConvId, effort });
      } else {
        runAgregador(text, priorMessages, effort);
      }
      return [...prev, { role: 'user', content: text }];
    });
    setScrollTrigger(n => n + 1);
  }, [mode, activeConvId, runOrquestrador, runAgregador]);

  const sendClarification = useCallback((answers: string) => {
    if (!clarification) return;
    setMessages(prev => [...prev, { role: 'user', content: answers }]);
    runOrquestrador({
      prompt: answers,
      conversation_id: clarification.conversationId,
      clarification_answers: answers,
    });
  }, [clarification, runOrquestrador]);

  const handleNew = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setStreaming(false);
    setActiveConvId(undefined);
    setClarification(null);
  }, []);

  const handleSelectConversation = useCallback(async (id: string) => {
    abortRef.current?.abort();
    setStreaming(false);
    setClarification(null);
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
                <EmptyState onSuggestion={sendMessage} userName={currentUser?.firstName} />
                <InputBar onSend={sendMessage} disabled={streaming} />
              </>
            )
          ) : (
            <>
              <ChatView messages={messages} streaming={streaming} scrollToBottomTrigger={scrollTrigger} />
              {showClarification
                ? <ClarificationPrompt onSend={sendClarification} />
                : <InputBar onSend={sendMessage} disabled={streaming || agregadorBlocked} />
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
    <Routes>
      <Route path="/cadastro" element={<RegisterPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/invite" element={<InvitePage />} />
      <Route path="/onboarding" element={<OnboardingPage />} />
      <Route path="/" element={
        <RequireAuth>
          <MainApp />
        </RequireAuth>
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
