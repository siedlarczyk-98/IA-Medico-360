/**
 * Estado e stream do chat, sem nenhuma aparência.
 *
 * POR QUE EXISTE
 * Até aqui tudo isto morava em `MainApp`, grudado no layout de desktop. A casca
 * mobile é outra árvore de componentes, e escrever a lógica de novo nela
 * reintroduziria, um por um, os bugs que custaram investigação: a corrida entre
 * conversas, o stream que picotava a resposta em vários balões, a pergunta
 * enviada entre `text_done` e `done` que apagava a resposta anterior.
 *
 * ONDE FICA
 * O hook é chamado em `MainApp`, ACIMA da troca de casca. Girar o celular troca
 * a casca inteira; se o estado morasse dentro dela, a resposta em andamento
 * morreria junto. O `AbortController`, o timer de flush e o id da mensagem em
 * streaming vivem em refs daqui, e sobrevivem à troca.
 *
 * COMO CHEGA NA CASCA
 * Por prop, não por context. O flush roda 10 vezes por segundo durante a
 * resposta; num context, cada flush re-renderizaria todo consumidor. Os
 * callbacks devolvidos são estáveis (useCallback) — o memo da Sidebar depende
 * disso.
 *
 * Sem efeitos, de propósito: tudo aqui é disparado por evento do usuário ou do
 * stream.
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { getConversation } from '../api/conversations';
import { ErroDeApi, mensagemDeErro, valeTentarDeNovo } from '../api/erros';
import { queryOrquestrador, streamQuery, type Message } from '../api/orquestrador';
import type { Attachment, Effort, OrchestratorMode } from '../components/InputBar';
import { sessaoExpirou } from '../lib/auth';
import {
  INTERVALO_DE_FLUSH_MS,
  chipModeFor,
  nextStreamMsgId,
  pubmedFromDone,
  type PendingClarification,
} from './transformacoes';

type ParametrosDeEnvio = Parameters<typeof streamQuery>[0] & { effort?: Effort; file_ids?: string[] };

export function useChatController() {
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
  const [scrollTrigger, setScrollTrigger] = useState(0);
  const [conversaAbertaTrigger, setConversaAbertaTrigger] = useState(0);
  const [carregandoConversa, setCarregandoConversa] = useState(false);
  const selecaoRef = useRef(0);
  const ultimoEnvioRef = useRef<ParametrosDeEnvio | null>(null);
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

  const runOrquestrador = useCallback(async (params: ParametrosDeEnvio) => {
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
      if (err instanceof ErroDeApi && err.status === 401) {
        // A pergunta não chegou ao servidor: volta para o campo depois da
        // reentrada, para o médico só tocar em enviar. Resposta a um pedido de
        // esclarecimento não volta — solta no campo, viraria pergunta nova sem
        // o contexto das perguntas que ela respondia.
        sessaoExpirou({
          pergunta: params.clarification_answers ? undefined : params.prompt,
          conversaId: params.conversation_id,
        });
      }
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
  }, [cancelFlush, scheduleFlush, queryClient]);


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
    } catch (err) {
      if (pedido !== selecaoRef.current) return;
      if (err instanceof ErroDeApi && err.status === 401) {
        // Sem `handleNew`: a tela iria para "Nova consulta" por um instante antes
        // da reentrada. Era o 401 engolido em silêncio — a conversa sumia.
        sessaoExpirou({ conversaId: id });
        return;
      }
      handleNew();
    }
  }, [handleNew]);

  return {
    messages,
    streaming,
    finalizing,
    activeConvId,
    selectedMode,
    scrollTrigger,
    conversaAbertaTrigger,
    carregandoConversa,
    usageTick,
    pendingFolderName,
    activeFolderName,
    topbarTitle,
    /** Conversa vazia e nada a caminho: a casca mostra a tela inicial. */
    vazio: messages.length === 0 && !streaming && !carregandoConversa,
    sendBlocked: streaming || carregandoConversa,
    showClarification: Boolean(clarification) && !streaming,
    sendMessage,
    sendClarification,
    tentarDeNovo,
    handleStop,
    handleNew,
    handleSelectConversation,
    setSelectedMode,
  };
}

export type ChatController = ReturnType<typeof useChatController>;
