/**
 * Casca mobile: a Consulta pensada para o telefone.
 *
 * Desenho: protótipo `design_handoff_medico360_mobile`, com os tamanhos de
 * texto dos tokens do projeto (ver `mobile.css`). O estado do chat NÃO mora
 * aqui — chega pronto em `chat`, de `useChatController`, que fica acima da
 * troca de casca. Girar o celular troca esta casca pela de desktop (ou o
 * contrário) sem derrubar a resposta em andamento.
 *
 * NAVEGAÇÃO
 * Dentro da Waid (app ou site): ☰ abre a gaveta com Histórico e Pastas — o
 * hospedeiro já tem barra de abas, e uma segunda empilhada roubaria ~110 px.
 * Fora dela (URL direta): barra de abas embaixo. Nos dois, a Consulta NUNCA é
 * desmontada; o resto abre por cima dela, e o botão voltar do Android fecha a
 * camada de cima (`camadas.ts`).
 *
 * CONTA
 * Fora da Waid é a quarta aba; dentro dela, uma folha aberta pelo rodapé da
 * gaveta. Editar perfil é uma folha por cima das duas.
 *
 * `default export` porque é carregada com `lazy()`: quem nunca vê a casca
 * mobile não baixa o código dela.
 */

import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { ChatView } from '../../components/ChatView';
import { ClarificationPrompt } from '../../components/ClarificationPrompt';
import type { ChatController } from '../../chat/useChatController';
import { useConversasEPastas } from '../../hooks/useConversasEPastas';
import { useTituloDaConversa } from '../../hooks/useTituloDaConversa';
import { esconderBalaoNaCascaMovel } from '../../lib/intercom';
import { useCurrentUser } from '../../lib/useCurrentUser';
import { BottomSheet } from './BottomSheet';
import { CabecalhoMovel } from './CabecalhoMovel';
import { ContaConteudo, SheetPerfil } from './Conta';
import { fecharTodasCamadas, voltarPara } from './camadas';
import { ComposerMovel } from './ComposerMovel';
import { ConsultaVazia } from './ConsultaVazia';
import { detectarHospedeiro } from './hospedeiro';
import { Icone } from './Icone';
import { BarraDeAbas, GavetaNavegacao, TelaNavegacao, type AbaInferior } from './Navegacao';
import { useCamada } from './useCamada';
import { useTeclado } from './useTeclado';
import './mobile.css';

/**
 * Viewport da casca mobile:
 * - `viewport-fit=cover` faz o `env(safe-area-inset-*)` valer alguma coisa
 *   (sem ele é sempre 0, e o conteúdo vai para baixo do notch deitado);
 * - `interactive-widget=resizes-content` faz o Chrome Android ENCOLHER o
 *   layout quando o teclado abre, em vez de só cobrir a página.
 *
 * Aplicado ao montar e desfeito ao sair, em vez de fixo no `index.html`: com a
 * casca mobile desligada, a interface de hoje não foi feita para o notch e
 * passaria a desenhar embaixo dele.
 */
const VIEWPORT_MOVEL = 'width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content';

function useAmbienteMovel() {
  useEffect(() => {
    // Recarregar a página com uma camada aberta deixa a entrada do histórico
    // marcada com profundidade, sem camada nenhuma na tela: o próximo voltar
    // "não faria nada". Zera a marca ao montar.
    const estado = window.history.state as Record<string, unknown> | null;
    if (estado && 'mvCamada' in estado) {
      const resto = { ...estado };
      delete resto.mvCamada;
      window.history.replaceState(resto, '');
    }
    const meta = document.querySelector<HTMLMetaElement>('meta[name="viewport"]');
    const antes = meta?.getAttribute('content') ?? null;
    meta?.setAttribute('content', VIEWPORT_MOVEL);
    // O balão do Intercom fica sobre o botão de enviar. O suporte, aqui, abre
    // pelo menu (Conta).
    esconderBalaoNaCascaMovel(true);
    return () => {
      if (meta && antes !== null) meta.setAttribute('content', antes);
      esconderBalaoNaCascaMovel(false);
    };
  }, []);
}

export default function MobileShell({ chat }: { chat: ChatController }) {
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  // Onde estamos não muda durante a sessão: calculado uma vez.
  const [hospedeiro] = useState(detectarHospedeiro);
  const hospedado = hospedeiro === 'hospedado';
  const gaveta = useCamada<true>();
  const telaPorCima = useCamada<Exclude<AbaInferior, 'consulta'>>();
  // Folha da conta (dentro da Waid) e do perfil: uma camada só, que troca de
  // conteúdo — "Editar perfil" dentro da folha da conta substitui a folha, não
  // empilha outra.
  const folhaDaConta = useCamada<'conta' | 'perfil'>();
  const refDoTeclado = useTeclado();

  useAmbienteMovel();

  const irParaConsulta = useCallback(() => fecharTodasCamadas(), []);
  // Criar uma pasta abre uma consulta nova dentro dela (`useConversasEPastas`):
  // a tela tem de voltar para a Consulta para mostrar isso.
  const { handleNew } = chat;
  const novaNaPasta = useCallback((folderId?: string, folderName?: string) => {
    handleNew(folderId, folderName);
    fecharTodasCamadas();
  }, [handleNew]);
  const dados = useConversasEPastas({ activeId: chat.activeConvId, onNew: novaNaPasta });

  function aoTocarAba(a: AbaInferior) {
    if (a === 'consulta') return irParaConsulta();
    // Com uma tela já por cima, desce até ela (fecha pasta/folha abertas) e troca.
    if (telaPorCima.valor) voltarPara(1, () => telaPorCima.abrir(a));
    else telaPorCima.abrir(a);
  }

  const { messages, streaming, activeFolderName, pendingFolderName } = chat;
  const tituloDaConversa = useTituloDaConversa(chat.activeConvId, chat.topbarTitle);
  const titulo = chat.vazio ? 'Nova consulta' : tituloDaConversa;

  return (
    <div ref={refDoTeclado} className="shell-movel" data-casca="mobile" data-hospedeiro={hospedeiro}>
      <div className="mv-area">
        {/* A Consulta: sempre montada. */}
        <div className="mv-consulta">
          <CabecalhoMovel
            titulo={titulo}
            mostrarMarca={!hospedado && chat.vazio}
            onMenu={hospedado ? () => gaveta.abrir(true) : undefined}
            onNova={chat.vazio ? undefined : () => chat.handleNew()}
          />

          {activeFolderName && messages.length > 0 && (
            <div className="mv-banner">
              <Icone n="folder" s={18} w={2} />
              <b>{activeFolderName}</b>
              <span>Outras conversas da pasta servem de contexto</span>
            </div>
          )}
          {pendingFolderName && messages.length === 0 && (
            <div className="mv-banner">
              <Icone n="folder" s={18} w={2} />
              <span>Nova consulta em <b>{pendingFolderName}</b></span>
            </div>
          )}

          <main className="mv-corpo">
            {chat.vazio ? (
              <ConsultaVazia chat={chat} nome={currentUser?.firstName} />
            ) : (
              <ChatView
                messages={messages}
                streaming={streaming}
                streamingMode={chat.selectedMode}
                finalizing={chat.finalizing}
                scrollToBottomTrigger={chat.scrollTrigger}
                conversationOpenedTrigger={chat.conversaAbertaTrigger}
                onRetry={chat.tentarDeNovo}
                loading={chat.carregandoConversa}
              />
            )}
          </main>

          {chat.showClarification
            ? <ClarificationPrompt onSend={chat.sendClarification} />
            : <ComposerMovel chat={chat} />}
        </div>

        {/* Fora da Waid: Histórico e Pastas por cima da Consulta. */}
        {!hospedado && (telaPorCima.valor === 'historico' || telaPorCima.valor === 'pastas') && (
          <TelaNavegacao aba={telaPorCima.valor} chat={chat} dados={dados} onIrParaConsulta={irParaConsulta} />
        )}
        {!hospedado && telaPorCima.valor === 'conta' && (
          <section className="mv-tela" aria-label="Conta">
            <h1 className="mv-titulo-grande">Conta</h1>
            <div className="mv-painel-corpo rolagem">
              <ContaConteudo hospedado={false} usageTick={chat.usageTick} onEditarPerfil={() => folhaDaConta.abrir('perfil')} />
            </div>
          </section>
        )}
      </div>

      {!hospedado && (
        <BarraDeAbas
          ativa={telaPorCima.valor ?? 'consulta'}
          respondendo={streaming}
          onAba={aoTocarAba}
        />
      )}

      {/* Dentro da Waid: a gaveta. */}
      {hospedado && gaveta.valor && (
        <GavetaNavegacao
          chat={chat}
          dados={dados}
          onIrParaConsulta={irParaConsulta}
          onFechar={() => gaveta.fechar()}
          onConta={() => folhaDaConta.abrir('conta')}
        />
      )}

      {folhaDaConta.valor === 'conta' && (
        <BottomSheet titulo="Conta" onFechar={() => folhaDaConta.fechar()}>
          <ContaConteudo hospedado={hospedado} usageTick={chat.usageTick} onEditarPerfil={() => folhaDaConta.abrir('perfil')} />
        </BottomSheet>
      )}
      {folhaDaConta.valor === 'perfil' && (
        <SheetPerfil
          hospedado={hospedado}
          onFechar={() => folhaDaConta.fechar()}
          onSalvo={() => queryClient.invalidateQueries({ queryKey: ['currentUser'] })}
        />
      )}
    </div>
  );
}
