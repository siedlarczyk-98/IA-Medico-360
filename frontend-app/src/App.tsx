import { useCallback, useRef, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Topbar } from './components/Topbar';
import { EmptyState } from './components/EmptyState';
import { ChatView } from './components/ChatView';
import { InputBar } from './components/InputBar';
import { ClarificationPrompt } from './components/ClarificationPrompt';
import { ModelSelector } from './components/ModelSelector';
import { streamQuery, queryOrquestrador, type Message } from './api/orquestrador';
import { streamAgregador } from './api/agregador';

type AppMode = 'orquestrador' | 'agregador';

interface PendingClarification {
  conversationId: string;
  questions: string[];
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [mode, setMode] = useState<AppMode>('orquestrador');
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | undefined>();
  const [clarification, setClarification] = useState<PendingClarification | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
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

  const runOrquestrador = useCallback(async (params: Parameters<typeof streamQuery>[0]) => {
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
    }
  }, []);

  const runAgregador = useCallback(async (prompt: string) => {
    if (selectedModels.length === 0) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);

    // Uma mensagem por modelo, identificada pelo model_id
    const buffers: Record<string, string> = {};

    try {
      for await (const event of streamAgregador(prompt, selectedModels, ctrl.signal)) {
        if (event.type === 'delta') {
          const mid = event.model_id;
          buffers[mid] = (buffers[mid] ?? '') + event.delta;
          setMessages(prev => {
            const next = [...prev];
            const idx = next.findIndex(m => m.role === 'assistant' && m.mode === mid);
            if (idx === -1) {
              next.push({ role: 'assistant', content: buffers[mid], mode: mid });
            } else {
              next[idx] = { ...next[idx], content: buffers[mid] };
            }
            return next;
          });
        }
        if (event.type === 'error') {
          setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${event.error ?? 'Erro no modelo'}` }]);
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Erro ao conectar com o servidor.' }]);
    } finally {
      setStreaming(false);
    }
  }, [selectedModels]);

  const sendMessage = useCallback((text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    if (mode === 'orquestrador') {
      runOrquestrador({ prompt: text, conversation_id: activeConvId });
    } else {
      runAgregador(text);
    }
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

  const handleModeChange = useCallback((m: AppMode) => {
    setMode(m);
    handleNew();
  }, [handleNew]);

  const showClarification = clarification && !streaming;
  const agregadorBlocked = mode === 'agregador' && selectedModels.length === 0;

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar activeId={activeConvId} onNew={handleNew} onSelect={setActiveConvId} open={sidebarOpen} onToggle={() => setSidebarOpen(o => !o)} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Topbar title={topbarTitle} mode={mode} onModeChange={handleModeChange} onMenuToggle={() => setSidebarOpen(o => !o)} />

        {mode === 'agregador' && (
          <ModelSelector selected={selectedModels} onChange={setSelectedModels} max={1} />
        )}

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {messages.length === 0 && !streaming ? (
            <>
              <EmptyState onSuggestion={agregadorBlocked ? () => {} : sendMessage} />
              <InputBar onSend={sendMessage} disabled={streaming || agregadorBlocked}
                placeholder={agregadorBlocked ? 'Selecione ao menos 1 modelo acima para começar.' : undefined} />
            </>
          ) : (
            <>
              <ChatView messages={messages} streaming={streaming} />
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

export default App;
