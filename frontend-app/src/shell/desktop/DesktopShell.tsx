/**
 * Casca de desktop: sidebar ao lado, chat no centro.
 *
 * É o layout que existia em `MainApp`, sem mudança de aparência. O estado do
 * chat NÃO mora aqui — chega pronto em `chat`, vindo de `useChatController`,
 * que fica acima da troca de casca. Aqui só mora o que é desta casca: a
 * sidebar aberta ou fechada.
 */

import { useCallback, useState } from 'react';

import { ChatView } from '../../components/ChatView';
import { ClarificationPrompt } from '../../components/ClarificationPrompt';
import { EmptyState } from '../../components/EmptyState';
import { InputBar } from '../../components/InputBar';
import { Sidebar } from '../../components/Sidebar';
import { Topbar } from '../../components/Topbar';
import type { ChatController } from '../../chat/useChatController';
import { useCurrentUser } from '../../lib/useCurrentUser';

interface Props {
  chat: ChatController;
  /**
   * Qual casca está usando este layout. A versão 0 da casca mobile reaproveita
   * este componente; o atributo deixa os testes (e o /diagnostico-embed)
   * saberem qual das duas está montada.
   */
  casca?: 'desktop' | 'mobile';
}

export function DesktopShell({ chat, casca = 'desktop' }: Props) {
  const currentUser = useCurrentUser();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Referência estável: inline, esta prop invalidaria o memo do Sidebar a cada
  // frame de streaming, re-renderizando toda a lista de conversas.
  const toggleSidebar = useCallback(() => setSidebarOpen(o => !o), []);

  const {
    messages, streaming, finalizing, selectedMode, scrollTrigger, conversaAbertaTrigger,
    carregandoConversa, pendingFolderName, activeFolderName, sendBlocked,
  } = chat;
  const onStop = streaming ? chat.handleStop : undefined;

  return (
    <div className="app-raiz" data-casca={casca} style={{ display: 'flex', overflow: 'hidden' }}>
      <Sidebar activeId={chat.activeConvId} onNew={chat.handleNew} onSelect={chat.handleSelectConversation} open={sidebarOpen} onToggle={toggleSidebar} usageTick={chat.usageTick} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Topbar title={chat.topbarTitle} onMenuToggle={toggleSidebar} />
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
          {chat.vazio ? (
            <>
              <EmptyState userName={currentUser?.firstName} onModeSelect={chat.setSelectedMode} selectedMode={selectedMode} />
              <InputBar onSend={chat.sendMessage} sendBlocked={sendBlocked} onStop={onStop} mode={selectedMode} onModeChange={chat.setSelectedMode} />
            </>
          ) : (
            <>
              <ChatView messages={messages} streaming={streaming} streamingMode={selectedMode} finalizing={finalizing} scrollToBottomTrigger={scrollTrigger} conversationOpenedTrigger={conversaAbertaTrigger} onRetry={chat.tentarDeNovo} loading={carregandoConversa} />
              {chat.showClarification
                ? <ClarificationPrompt onSend={chat.sendClarification} />
                : <InputBar onSend={chat.sendMessage} sendBlocked={sendBlocked} onStop={onStop} mode={selectedMode} onModeChange={chat.setSelectedMode} />
              }
            </>
          )}
        </div>
      </div>
    </div>
  );
}
