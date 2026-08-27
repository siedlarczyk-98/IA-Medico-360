import { lazy, Suspense, useCallback, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { Topbar } from './components/Topbar';
import { EmptyState } from './components/EmptyState';
import { ChatView } from './components/ChatView';
import { InputBar } from './components/InputBar';
import { ClarificationPrompt } from './components/ClarificationPrompt';
import type { Effort, OrchestratorMode, Attachment } from './components/InputBar';
import { streamQuery, queryOrquestrador, type Message, type StreamEvent, type PubmedValidation } from './api/orquestrador';
import { isAuthenticated, isTokenExpired } from './lib/auth';
import { useCurrentUser } from './lib/useCurrentUser';
import { getConversation } from './api/conversations';

// Páginas de auth são carregadas sob demanda (não fazem parte da rota principal).
const LoginPage = lazy(() => import('./pages/LoginPage').then(m => ({ default: m.LoginPage })));
const InvitePage = lazy(() => import('./pages/InvitePage').then(m => ({ default: m.InvitePage })));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage').then(m => ({ default: m.OnboardingPage })));
const RegisterPage = lazy(() => import('./pages/RegisterPage').then(m => ({ default: m.RegisterPage })));
const EmbedAuthPage = lazy(() => import('./pages/EmbedAuthPage').then(m => ({ default: m.EmbedAuthPage })));

const BACKEND_TO_CHIP: Record<string, string> = {
  QUICK_SEARCH:      'busca',
  CLINICAL_REASONING:'raciocinio',
  PHARMA_CHECK:      'farmaco',
  PHARMA_BULA:       'farmaco',
  PHARMA_RECEITA:    'farmaco',
  PHARMA_GENERICO:   'farmaco',
  PRODUCTIVITY:      'produtividade',
  EXAM_REVIEW:       'exames',
};

// Identidade da mensagem em streaming. Contador de módulo, e não crypto.randomUUID(),
// porque o valor precisa ser gerado de forma síncrona em qualquer ambiente (o
// jsdom dos testes inclusive) e só precisa ser único dentro da aba.
let streamMsgSeq = 0;
function nextStreamMsgId(): string {
  streamMsgSeq += 1;
  return `stream-${streamMsgSeq}`;
}

// OFF_TOPIC (saudações/mensagens triviais) não ganha badge — é só uma resposta simples.
function chipModeFor(mode: string): string | undefined {
  if (mode === 'OFF_TOPIC') return undefined;
  return BACKEND_TO_CHIP[mode] ?? mode;
}

/**
 * Converte as listas do PubMed do formato do evento `done` para o formato que
 * a ChatView consome. Devolve undefined quando não há nada — um bloco
 * "Referências verificadas" vazio é pior que bloco nenhum.
 *
 * Sem isto o orquestrador nunca exibia PubMed: o dado vinha no `done`, mas só
 * o agregador o convertia. O bloco existia na ChatView sem ninguém alimentá-lo.
 */
function pubmedFromDone(
  event: Extract<StreamEvent, { type: 'done' | 'cache_hit' }>,
): PubmedValidation | undefined {
  const cited = (event.cited_guidelines_verified ?? []).map(c => ({
    title: c.title, pmid: c.pmid, verified: c.verified,
  }));
  const newer = (event.newer_guidelines_found ?? []).map(a => ({
    pmid: a.pmid,
    article_title: a.article_title ?? a.title ?? '',
    abstract_snippet: a.abstract_snippet ?? '',
  }));
  if (cited.length === 0 && newer.length === 0) return undefined;
  return { cited_verified: cited, newer_guidelines: newer };
}

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
  const [activeConvId, setActiveConvId] = useState<string | undefined>();
  const [clarification, setClarification] = useState<PendingClarification | null>(null);
  const [selectedMode, setSelectedMode] = useState<OrchestratorMode>('QUICK_SEARCH');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [scrollTrigger, setScrollTrigger] = useState(0);
  const [usageTick, setUsageTick] = useState(0);
  const pendingFolderIdRef = useRef<string | undefined>(undefined);
  const pendingFolderNameRef = useRef<string | undefined>(undefined);
  // O anexo em edição não é mais espelhado em estado do App: ele só servia para
  // as checagens de visão do Agregador. O InputBar já entrega o anexo direto ao
  // `sendMessage`, que é quem precisa dele.
  const [pendingFolderName, setPendingFolderName] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);

  // Id da mensagem de assistente em streaming, para removê-la se o stream for
  // abortado no meio. Guardamos o id e não o índice: índice envelhece assim que
  // qualquer outra mensagem entra na lista.
  const streamMsgIdRef = useRef<string | null>(null);
  // Ref sempre atual das mensagens — evita recriar `sendMessage` a cada token.
  // A regra `react-hooks/refs` reclama de escrita em ref durante o render, e em
  // geral tem razao. Aqui a alternativa (atribuir num useEffect) faz a ref
  // ATRASAR um render, e os handlers de streaming leem `messagesRef.current`
  // esperando o valor corrente — o "conserto" introduziria bug de mensagem
  // perdida. Mantido de propósito.
  const messagesRef = useRef<Message[]>(messages);
  // eslint-disable-next-line react-hooks/refs
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

  const runOrquestrador = useCallback(async (params: Parameters<typeof streamQuery>[0] & { effort?: Effort; priorMessages?: Message[]; file_ids?: string[] }) => {
    abortRef.current?.abort();
    cancelFlush();

    // Remove a mensagem parcial deixada por um stream anterior abortado.
    // Filtra pelo id em vez de truncar a lista a partir de um índice: o índice
    // antigo derrubaria junto qualquer mensagem que tenha entrado depois dele.
    const prevStreamId = streamMsgIdRef.current;
    if (prevStreamId !== null) {
      setMessages(prev => prev.filter(m => m.id !== prevStreamId));
      streamMsgIdRef.current = null;
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    setClarification(null);

    const acc = { current: '' };
    // Atribuído de forma SÍNCRONA na chegada do primeiro token (ver abaixo).
    // Já foi um índice resolvido dentro do updater do setMessages, o que criava
    // uma mensagem nova a cada token que chegasse antes do React processar a
    // atualização anterior — a resposta saía picotada em vários balões.
    let assistantId: string | null = null;

    // Localiza a mensagem pelo id. Devolve -1 se ela já não estiver na lista
    // (conversa trocada, stream abortado), e nesse caso o update é descartado.
    const indexOfAssistant = (list: Message[]) =>
      assistantId === null ? -1 : list.findIndex(m => m.id === assistantId);

    const flushAssistant = () => {
      if (assistantId === null) return;
      setMessages(prev => {
        const idx = indexOfAssistant(prev);
        if (idx === -1) return prev;
        const next = [...prev];
        next[idx] = { ...next[idx], content: acc.current };
        return next;
      });
    };

    const history = (params.priorMessages ?? []).map(m => ({ role: m.role, content: m.content }));
    const folder_id = pendingFolderIdRef.current;

    try {
      for await (const event of streamQuery({ ...params, history, folder_id, file_ids: params.file_ids }, ctrl.signal)) {
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
          const chipMode = chipModeFor(event.mode);
          const cachedPubmed = pubmedFromDone(event);
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: event.response_text,
            mode: chipMode,
            ...(event.citations && event.citations.length > 0 ? { citations: event.citations } : {}),
            ...(cachedPubmed ? { pubmed_validation: cachedPubmed } : {}),
          }]);
          return;
        }
        if (event.type === 'token') {
          acc.current += event.text;
          if (assistantId === null) {
            // A marcação acontece AQUI, fora do updater, para que o próximo
            // token já veja `assistantId` preenchido mesmo que o React ainda
            // não tenha aplicado este setMessages. O updater fica puro — o que
            // também o torna seguro sob a dupla invocação do StrictMode.
            const id = nextStreamMsgId();
            assistantId = id;
            streamMsgIdRef.current = id;
            setMessages(prev => [...prev, { id, role: 'assistant', content: acc.current }]);
          } else {
            scheduleFlush(flushAssistant);
          }
        }
        if (event.type === 'done') {
          setActiveConvId(event.conversation_id);
          pendingFolderIdRef.current = undefined;
          setPendingFolderName(undefined);
          queryClient.invalidateQueries({ queryKey: ['conversations'] });
          const chipMode = chipModeFor(event.mode);
          const pubmed = pubmedFromDone(event);
          if (assistantId !== null) {
            setMessages(prev => {
              const idx = indexOfAssistant(prev);
              if (idx === -1) return prev;
              const next = [...prev];
              next[idx] = {
                ...next[idx],
                mode: chipMode,
                ...(event.citations && event.citations.length > 0 ? { citations: event.citations } : {}),
                ...(pubmed ? { pubmed_validation: pubmed } : {}),
              };
              return next;
            });
          }
        }
        if (event.type === 'error') {
          if (event.status === 'unsupported_mode') {
            // Modos PharmaDB não suportam streaming — fallback para /query
            const result = await queryOrquestrador({ ...params, folder_id });
            const chipMode = chipModeFor(result.mode);
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
      // Só limpa se a ref ainda apontar para ESTE stream. Num abort, quem
      // aborta já leu a ref e a reatribuiu antes deste `finally` rodar —
      // limpar sem checar apagaria a marcação do stream que acabou de começar.
      if (streamMsgIdRef.current === assistantId) streamMsgIdRef.current = null;
      setStreaming(false);
      setUsageTick(t => t + 1);
    }
  }, [cancelFlush, scheduleFlush]);


  const sendMessage = useCallback((text: string, effort: Effort = 'detalhado', attachments?: Attachment[]) => {
    const priorMessages = messagesRef.current;
    runOrquestrador({
      prompt: text, conversation_id: activeConvId, effort, mode: selectedMode, priorMessages,
      file_ids: attachments?.map(a => a.fileId),
    });
    setMessages(prev => [...prev, {
      role: 'user',
      content: text,
      attachments: attachments?.map(a => ({ id: a.fileId, file_name: a.name, file_type: a.fileType })),
    }]);
    setScrollTrigger(n => n + 1);
  }, [activeConvId, selectedMode, runOrquestrador]);

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
      // O backend devolve o modo cru ("PRODUCTIVITY"); ao vivo a mensagem passa
      // por chipModeFor. Sem esta conversão a conversa reaberta mostrava o nome
      // interno do modo no lugar do chip — mesma resposta com duas aparências.
      setMessages(detail.messages.map(m =>
        m.role === 'assistant' && m.mode
          ? { ...m, mode: chipModeFor(m.mode) }
          : m
      ));
      setActiveConvId(detail.id);
    } catch {
      handleNew();
    }
  }, [handleNew]);

  // Referência estável: inline, esta prop invalidaria o memo do Sidebar a cada
  // frame de streaming, re-renderizando toda a lista de conversas.
  const toggleSidebar = useCallback(() => setSidebarOpen(o => !o), []);

  const showClarification = clarification && !streaming;

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar activeId={activeConvId} onNew={handleNew} onSelect={handleSelectConversation} open={sidebarOpen} onToggle={toggleSidebar} usageTick={usageTick} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Topbar title={topbarTitle} onMenuToggle={toggleSidebar} />
        {pendingFolderName && messages.length === 0 && (
          <div style={{ padding: '6px 20px', background: 'var(--fill2)', borderBottom: '1px solid var(--line2)', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--pen2)' }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path d="M2 4h5l1.5 2H14v7H2V4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            Nova consulta em <strong style={{ color: 'var(--ink)' }}>{pendingFolderName}</strong>
          </div>
        )}

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {messages.length === 0 && !streaming ? (
            <>
              <EmptyState userName={currentUser?.firstName} onModeSelect={setSelectedMode} selectedMode={selectedMode} />
              <InputBar onSend={sendMessage} disabled={streaming} mode={selectedMode} onModeChange={setSelectedMode} />
            </>
          ) : (
            <>
              <ChatView messages={messages} streaming={streaming} streamingMode={selectedMode} scrollToBottomTrigger={scrollTrigger} />
              {showClarification
                ? <ClarificationPrompt onSend={sendClarification} />
                : <InputBar onSend={sendMessage} disabled={streaming} mode={selectedMode} onModeChange={setSelectedMode} />
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
