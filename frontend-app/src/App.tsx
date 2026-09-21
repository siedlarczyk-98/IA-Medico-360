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
import { mensagemDeErro, valeTentarDeNovo } from './api/erros';
import { OnboardingGate } from '@shared/onboarding/OnboardingGate';
import { getToken, isAuthenticated, isTokenExpired, setToken } from './lib/auth';

// Mesma convenção dos módulos de `api/`: o backend por env, sem barra final.
const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
import { useCurrentUser } from './lib/useCurrentUser';
import { getConversation } from './api/conversations';

/** Intervalo entre atualizações do texto em streaming. Ver `scheduleFlush`. */
const INTERVALO_DE_FLUSH_MS = 100;

// Páginas de auth são carregadas sob demanda (não fazem parte da rota principal).
const LoginPage = lazy(() => import('./pages/LoginPage').then(m => ({ default: m.LoginPage })));
const InvitePage = lazy(() => import('./pages/InvitePage').then(m => ({ default: m.InvitePage })));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage').then(m => ({ default: m.OnboardingPage })));
const RegisterPage = lazy(() => import('./pages/RegisterPage').then(m => ({ default: m.RegisterPage })));
const EmbedAuthPage = lazy(() => import('./pages/EmbedAuthPage').then(m => ({ default: m.EmbedAuthPage })));
// Tela técnica, sem link em lugar nenhum: só é alcançada por quem digita a rota
// ou por uma seção da Waid apontada para ela. Ver o docblock do arquivo.
const DiagnosticoEmbedPage = lazy(() => import('./pages/DiagnosticoEmbedPage').then(m => ({ default: m.DiagnosticoEmbedPage })));

const BACKEND_TO_CHIP: Record<string, string> = {
  QUICK_SEARCH:      'busca',
  CLINICAL_REASONING:'raciocinio',
  PHARMA_CHECK:      'farmaco',
  PHARMA_BULA:       'farmaco',
  PHARMA_RECEITA:    'farmaco',
  PHARMA_GENERICO:   'farmaco',
  PRODUCTIVITY:      'produtividade',
  EXAM_REVIEW:       'exames',
  DATA_OCEAN:        'dados',
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
  // Separado de `streaming` de propósito: entre `text_done` e `done` o texto já
  // está inteiro na tela e só faltam metadados (PubMed, especialidade). Esse
  // intervalo não pode bloquear a digitação — a resposta parece pronta porque
  // está pronta.
  const [finalizing, setFinalizing] = useState(false);
  const [activeConvId, setActiveConvId] = useState<string | undefined>();
  const [clarification, setClarification] = useState<PendingClarification | null>(null);
  const [selectedMode, setSelectedMode] = useState<OrchestratorMode>('QUICK_SEARCH');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [scrollTrigger, setScrollTrigger] = useState(0);
  const [conversaAbertaTrigger, setConversaAbertaTrigger] = useState(0);
  const [carregandoConversa, setCarregandoConversa] = useState(false);
  const selecaoRef = useRef(0);
  const ultimoEnvioRef = useRef<(Parameters<typeof streamQuery>[0] & { effort?: Effort; file_ids?: string[] }) | null>(null);
  const [usageTick, setUsageTick] = useState(0);
  const pendingFolderIdRef = useRef<string | undefined>(undefined);
  // Pasta onde uma conversa NOVA vai nascer. Só rótulo — o id que vai no
  // payload é o `pendingFolderIdRef` acima.
  const [pendingFolderName, setPendingFolderName] = useState<string | undefined>();
  // Pasta da conversa ABERTA (diferente de `pendingFolderName`, que é a pasta
  // onde uma conversa nova vai nascer). Alimenta o aviso de contexto cruzado.
  const [activeFolderName, setActiveFolderName] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);

  // Id da mensagem de assistente em streaming, para removê-la se o stream for
  // abortado no meio. Guardamos o id e não o índice: índice envelhece assim que
  // qualquer outra mensagem entra na lista.
  const streamMsgIdRef = useRef<string | null>(null);
  // Flush em lote dos tokens de streaming: acumulamos em refs e aplicamos ao
  // state a cada `INTERVALO_DE_FLUSH_MS`, evitando re-render por token.
  //
  // Era uma vez por QUADRO (requestAnimationFrame). Só que cada flush faz o
  // Markdown da resposta inteira ser interpretado de novo, e esse custo cresce
  // com o texto: no terço final de uma resposta longa, 60 reinterpretações por
  // segundo engasgavam a tela — pior no celular e dentro do iframe. A 10 por
  // segundo o texto continua parecendo contínuo e o trabalho cai seis vezes.
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelFlush = useCallback(() => {
    if (flushTimerRef.current != null) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  }, []);

  const scheduleFlush = useCallback((flush: () => void) => {
    if (flushTimerRef.current != null) return;
    flushTimerRef.current = setTimeout(() => {
      flushTimerRef.current = null;
      flush();
    }, INTERVALO_DE_FLUSH_MS);
  }, []);

  const topbarTitle = useMemo(() =>
    messages.length === 0
      ? 'Nova consulta'
      : (messages.find(m => m.role === 'user')?.content.slice(0, 60) ?? '') + '…',
    [messages]
  );

  const runOrquestrador = useCallback(async (params: Parameters<typeof streamQuery>[0] & { effort?: Effort; file_ids?: string[] }) => {
    abortRef.current?.abort();
    cancelFlush();
    ultimoEnvioRef.current = params;

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
    setFinalizing(false);
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

    const folder_id = pendingFolderIdRef.current;

    try {
      for await (const event of streamQuery({ ...params, folder_id, file_ids: params.file_ids }, ctrl.signal)) {
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
        if (event.type === 'text_done') {
          // A conversa precisa ser fixada JUNTO com a liberação do input. Se o
          // médico mandar a próxima pergunta antes do `done`, sem isto ela iria
          // sem conversation_id e abriria uma conversa nova.
          setActiveConvId(event.conversation_id);
          pendingFolderIdRef.current = undefined;
          setPendingFolderName(undefined);
          queryClient.invalidateQueries({ queryKey: ['conversations'] });
          // O texto está COMPLETO a partir daqui: o que resta até o `done` são
          // metadados (citações, PubMed). Então a marcação de "mensagem em
          // streaming" sai agora, junto com a liberação do campo — e não no
          // `finally`. Enquanto ela ficava, uma pergunta enviada nesta janela
          // tratava a resposta concluída como parcial de um stream abortado e a
          // REMOVIA da tela; o médico perdia o que estava lendo.
          cancelFlush();
          flushAssistant();
          if (streamMsgIdRef.current === assistantId) streamMsgIdRef.current = null;
          setStreaming(false);
          setFinalizing(true);
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
                is_fallback: event.is_fallback,
              };
              return next;
            });
          }
          setFinalizing(false);
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
      // A frase depende do QUE falhou: cota semanal, sessão expirada e queda de
      // rede pedem reações diferentes do médico. Ver `api/erros.ts`.
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `⚠️ ${mensagemDeErro(err)}`,
        podeTentarDeNovo: valeTentarDeNovo(err),
      }]);
    } finally {
      cancelFlush();
      flushAssistant();
      // Só limpa se a ref ainda apontar para ESTE stream. Num abort, quem
      // aborta já leu a ref e a reatribuiu antes deste `finally` rodar —
      // limpar sem checar apagaria a marcação do stream que acabou de começar.
      if (streamMsgIdRef.current === assistantId) streamMsgIdRef.current = null;
      // Mesma regra para os indicadores: só mexe quem ainda é o stream atual.
      // Um stream abortado por uma pergunta nova termina DEPOIS de o novo ter
      // ligado `streaming`; sem esta checagem ele o desligava, e o campo ficava
      // liberado no meio da resposta nova.
      if (abortRef.current === ctrl) {
        setStreaming(false);
        setFinalizing(false);
      }
      setUsageTick(t => t + 1);
    }
  }, [cancelFlush, scheduleFlush]);


  // O anexo em edição não é espelhado em estado do App: ele só servia para as
  // checagens de visão do Agregador. O InputBar entrega o anexo direto aqui,
  // que é quem precisa dele.
  const sendMessage = useCallback((text: string, effort: Effort = 'detalhado', attachments?: Attachment[]) => {
    runOrquestrador({
      prompt: text, conversation_id: activeConvId, effort, mode: selectedMode,
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

  /**
   * "Tentar novamente": repete o último envio, sem o médico redigitar. Tira o
   * aviso de erro da tela primeiro; a pergunta dele continua lá.
   */
  const tentarDeNovo = useCallback(() => {
    const params = ultimoEnvioRef.current;
    if (!params) return;
    setMessages(prev => prev.filter(m => !m.podeTentarDeNovo));
    void runOrquestrador(params);
  }, [runOrquestrador]);

  /** "Parar": cancela a resposta em andamento. O texto já recebido fica na tela. */
  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
    setFinalizing(false);
  }, []);

  const handleNew = useCallback((folderId?: string, folderName?: string) => {
    abortRef.current?.abort();
    selecaoRef.current += 1; // uma conversa ainda carregando não pode cair em cima desta
    setCarregandoConversa(false);
    setMessages([]);
    setStreaming(false);
    setFinalizing(false);
    setActiveConvId(undefined);
    setClarification(null);
    setActiveFolderName(folderName);
    setSelectedMode('QUICK_SEARCH');
    pendingFolderIdRef.current = folderId;
    setPendingFolderName(folderName);
  }, []);

  const handleSelectConversation = useCallback(async (id: string) => {
    abortRef.current?.abort();
    // CORRIDA: clicar em duas conversas em sequência disparava dois pedidos, e a
    // resposta que chegasse POR ÚLTIMO ganhava — que não é necessariamente a do
    // último clique. O médico clicava na conversa B e via a A, com o título da B
    // destacado na lateral. Cada clique ganha um número; resposta de número velho
    // é descartada.
    const pedido = ++selecaoRef.current;
    // Resposta imediata ao clique: a lateral já destaca a conversa e a área
    // central mostra que está carregando. Antes não acontecia NADA até a rede
    // responder.
    setActiveConvId(id);
    setMessages([]);
    setCarregandoConversa(true);
    setStreaming(false);
    setFinalizing(false);
    setClarification(null);
    pendingFolderIdRef.current = undefined;
    setPendingFolderName(undefined);
    try {
      const detail = await getConversation(id);
      if (pedido !== selecaoRef.current) return;
      // O backend devolve o modo cru ("PRODUCTIVITY"); ao vivo a mensagem passa
      // por chipModeFor. Sem esta conversão a conversa reaberta mostrava o nome
      // interno do modo no lugar do chip — mesma resposta com duas aparências.
      setMessages(detail.messages.map(m =>
        m.role === 'assistant' && m.mode
          ? { ...m, mode: chipModeFor(m.mode) }
          : m
      ));
      setActiveConvId(detail.id);
      setActiveFolderName(detail.folder_name ?? undefined);
      setConversaAbertaTrigger(n => n + 1);
      setCarregandoConversa(false);
    } catch {
      if (pedido === selecaoRef.current) handleNew();
    }
  }, [handleNew]);

  // Referência estável: inline, esta prop invalidaria o memo do Sidebar a cada
  // frame de streaming, re-renderizando toda a lista de conversas.
  const toggleSidebar = useCallback(() => setSidebarOpen(o => !o), []);

  const showClarification = clarification && !streaming;

  return (
    <div className="app-raiz" style={{ display: 'flex', overflow: 'hidden' }}>
      <Sidebar activeId={activeConvId} onNew={handleNew} onSelect={handleSelectConversation} open={sidebarOpen} onToggle={toggleSidebar} usageTick={usageTick} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Topbar title={topbarTitle} onMenuToggle={toggleSidebar} />
        {activeFolderName && messages.length > 0 && (
          <div style={{ padding: '6px 20px', background: 'var(--fill2)', borderBottom: '1px solid var(--line2)', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--pen2)' }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path d="M2 4h5l1.5 2H14v7H2V4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            Pode usar outras conversas da pasta <strong style={{ color: 'var(--ink)' }}>{activeFolderName}</strong> como contexto
          </div>
        )}

        {pendingFolderName && messages.length === 0 && (
          <div style={{ padding: '6px 20px', background: 'var(--fill2)', borderBottom: '1px solid var(--line2)', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--pen2)' }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path d="M2 4h5l1.5 2H14v7H2V4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            Nova consulta em <strong style={{ color: 'var(--ink)' }}>{pendingFolderName}</strong>
          </div>
        )}

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {messages.length === 0 && !streaming && !carregandoConversa ? (
            <>
              <EmptyState userName={currentUser?.firstName} onModeSelect={setSelectedMode} selectedMode={selectedMode} />
              <InputBar onSend={sendMessage} sendBlocked={streaming || carregandoConversa} onStop={streaming ? handleStop : undefined} mode={selectedMode} onModeChange={setSelectedMode} />
            </>
          ) : (
            <>
              <ChatView messages={messages} streaming={streaming} streamingMode={selectedMode} finalizing={finalizing} scrollToBottomTrigger={scrollTrigger} conversationOpenedTrigger={conversaAbertaTrigger} onRetry={tentarDeNovo} loading={carregandoConversa} />
              {showClarification
                ? <ClarificationPrompt onSend={sendClarification} />
                : <InputBar onSend={sendMessage} sendBlocked={streaming || carregandoConversa} onStop={streaming ? handleStop : undefined} mode={selectedMode} onModeChange={setSelectedMode} />
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
        <Route path="/diagnostico-embed" element={<DiagnosticoEmbedPage />} />
        <Route path="/" element={
          <RequireAuth>
            {/*
              O gate lê `onboarding_pendencias` do servidor — nenhum app decide
              o que falta. Fica AQUI, e não só no /login, porque antes a decisão
              acontecia apenas no momento do login: bastava navegar direto para
              "/" para pular o onboarding inteiro.
            */}
            <OnboardingGate
              apiBase={API_BASE}
              token={getToken()}
              aoConcluir={t => { setToken(t); window.location.reload(); }}
            >
              <MainApp />
            </OnboardingGate>
          </RequireAuth>
        } />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
