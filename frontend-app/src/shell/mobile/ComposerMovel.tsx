/**
 * Campo de pergunta da casca mobile.
 *
 * As REGRAS são as do desktop (`useComposer`): limite de anexos, tamanho,
 * consentimento de imagem, envio bloqueado durante a extração. O que muda é a
 * forma, pensada para o polegar e para a altura curta do webview da Waid:
 *
 * - uma caixa só, que cresce até ~5 linhas e depois rola por dentro;
 * - o modo vira um chip que abre uma folha, em vez de seis botões em fila;
 * - anexos numa faixa que rola de lado, em vez de quebrar linhas;
 * - Enter quebra linha (o Enter do teclado virtual é parágrafo; enviar ali
 *   partiria caso clínico longo), e o envio é pelo botão.
 *
 * Os nomes acessíveis ("Enviar", "Parar", "Anexar arquivos", o placeholder)
 * são os mesmos do desktop de propósito: os testes de comportamento rodam
 * contra as duas cascas pelo mesmo nome.
 */

import { useLayoutEffect, useRef, useState } from 'react';

import { ACCEPTED_FILE_TYPES } from '../../api/uploads';
import type { ChatController } from '../../chat/useChatController';
import { lerRascunho } from '../../chat/rascunho';
import { useComposer } from '../../chat/useComposer';
import { tratarEnterParaEnviar } from '../../lib/enterParaEnviar';
import { abrirCamada, fecharCamada, trocarCamada } from './camadas';
import { Icone } from './Icone';
import { modo as dadosDoModo } from './modos';
import { SheetConsentimento } from './SheetConsentimento';
import { SheetModo } from './SheetModo';
import { useCamada } from './useCamada';

/** ~5 linhas de 24 px + respiro. Acima disso, rola dentro da caixa. */
const ALTURA_MAX_CAMPO = 140;

const ROTULO_DO_TIPO: Record<string, string> = {
  pdf: 'PDF', docx: 'Word', xlsx: 'Excel', image: 'Imagem',
};

export function ComposerMovel({ chat }: { chat: ChatController }) {
  const composer = useComposer({ onSend: chat.sendMessage, sendBlocked: chat.sendBlocked });
  const folhaDeModo = useCamada<true>();
  // O aviso de imagem abre pelo store do rascunho (ver `useComposer`), não por
  // um clique aqui. Guardamos se ELE está na pilha de camadas, para o
  // cancelar/confirmar saber se volta pelo histórico ou age direto (o aviso
  // pode ter vindo de antes de uma troca de casca, sem camada).
  const consentimentoNaPilha = useRef(false);
  const campoRef = useRef<HTMLTextAreaElement>(null);
  const arquivoRef = useRef<HTMLInputElement>(null);
  const [focado, setFocado] = useState(false);

  const m = dadosDoModo(chat.selectedMode);

  // A altura acompanha o TEXTO, venha ele da digitação, de uma sugestão tocada
  // na tela vazia ou do rascunho que sobreviveu à troca de casca. Layout effect
  // para medir antes da pintura: sem ele o campo aparece com uma linha e pula.
  useLayoutEffect(() => {
    const el = campoRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, ALTURA_MAX_CAMPO) + 'px';
  }, [composer.texto]);

  function enviar() {
    composer.submit();
  }

  return (
    <div className="mv-composer">
      {composer.anexos.filter(a => a.warning).map(a => (
        // Visível, não em tooltip: o médico precisa ver ANTES de enviar que o
        // arquivo não rendeu texto (PDF digitalizado, por exemplo).
        <div key={`aviso-${a.fileId}`} className="mv-nota mv-nota-alerta" data-testid="anexo-aviso">
          <Icone n="alert" s={16} /><span><strong>{a.name}</strong> — {a.warning}</span>
        </div>
      ))}

      <div className={'mv-cbox' + (focado ? ' focus' : '')}>
        {(composer.anexos.length > 0 || composer.envio !== 'idle') && (
          <div className="mv-atts rolagem-lateral">
            {composer.anexos.map(a => (
              <div key={a.fileId} className="mv-att" data-testid="anexo-chip">
                <span className="mv-att-i"><Icone n={a.warning ? 'alert' : a.fileType === 'image' ? 'image' : 'file'} s={18} /></span>
                <span className="mv-att-t"><b>{a.name}</b><span>{ROTULO_DO_TIPO[a.fileType] ?? 'Arquivo'}</span></span>
                <button type="button" className="mv-ib mv-att-x" aria-label={`Remover ${a.name}`} onClick={() => composer.removerAnexo(a.fileId)}>
                  <Icone n="x" s={18} />
                </button>
              </div>
            ))}
            {composer.envio === 'loading' && (
              <div className="mv-att">
                <span className="mv-att-i"><span className="mv-spin" /></span>
                <span className="mv-att-t"><b>Processando…</b><span>Lendo o arquivo</span></span>
              </div>
            )}
            {composer.envio === 'error' && (
              <div className="mv-att mv-att-err" role="alert">
                <span className="mv-att-i"><Icone n="alert" s={18} /></span>
                <span className="mv-att-t mv-att-t-livre"><span>{composer.erroDeEnvio}</span></span>
                <button type="button" className="mv-ib mv-att-x" aria-label="Descartar erro" onClick={composer.descartarErro}>
                  <Icone n="x" s={18} />
                </button>
              </div>
            )}
          </div>
        )}

        <textarea
          ref={campoRef}
          className="mv-campo"
          rows={1}
          value={composer.texto}
          onChange={e => composer.mudarTexto(e.target.value)}
          onKeyDown={e => tratarEnterParaEnviar(e, { isMobile: true, submit: enviar })}
          onFocus={() => setFocado(true)}
          onBlur={() => setFocado(false)}
          placeholder="Digite sua pergunta…"
          style={{ maxHeight: ALTURA_MAX_CAMPO }}
        />

        <div className="mv-cbar">
          <input
            ref={arquivoRef}
            type="file"
            multiple
            accept={ACCEPTED_FILE_TYPES}
            onChange={e => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = '';
              composer.adicionarArquivos(files);
              if (lerRascunho().imagensPendentes) {
                // Voltar com o aviso aberto = cancelar o envio da imagem.
                abrirCamada(() => { consentimentoNaPilha.current = false; composer.cancelarImagens(); });
                consentimentoNaPilha.current = true;
              }
            }}
            hidden
          />
          <button
            type="button"
            className="mv-ib"
            aria-label="Anexar arquivos"
            disabled={composer.extraindo || composer.lotado}
            onClick={() => arquivoRef.current?.click()}
          >
            <Icone n="clip" />
          </button>

          <button
            type="button"
            className="mv-modo"
            aria-label={`Modo: ${m.nome}, ${composer.esforco}. Trocar modo e esforço`}
            onClick={() => folhaDeModo.abrir(true)}
          >
            <Icone n={m.icone} s={18} />
            <span>{m.nome}</span>
            <Icone n="chevD" s={16} />
          </button>

          {chat.streaming ? (
            // Uma resposta leva de poucos segundos a quase um minuto. Sem
            // "Parar", quem mandou a pergunta errada esperava tudo isso.
            <button type="button" className="mv-send" aria-label="Parar" onClick={chat.handleStop}>
              <Icone n="stop" s={24} />
            </button>
          ) : (
            <button
              type="button"
              className={'mv-send' + (composer.podeEnviar ? '' : ' off')}
              aria-label="Enviar"
              disabled={!composer.podeEnviar}
              title={composer.extraindo ? 'Aguarde o processamento do anexo' : undefined}
              onClick={enviar}
            >
              <Icone n="up" w={2.2} />
            </button>
          )}
        </div>
      </div>

      {folhaDeModo.valor && (
        <SheetModo
          modo={chat.selectedMode}
          esforco={composer.esforco}
          onFechar={() => folhaDeModo.fechar()}
          onAplicar={(novoModo, novoEsforco) => {
            chat.setSelectedMode(novoModo);
            composer.mudarEsforco(novoEsforco);
            folhaDeModo.fechar();
          }}
        />
      )}

      {composer.imagensPendentes && (
        <SheetConsentimento
          arquivos={composer.imagensPendentes}
          onCancelar={() => {
            if (consentimentoNaPilha.current) fecharCamada();
            else composer.cancelarImagens();
          }}
          onEnviar={() => {
            if (!consentimentoNaPilha.current) {
              composer.confirmarImagens();
              return;
            }
            // Sai da pilha SEM cancelar (troca quem fecha) e só então envia.
            trocarCamada(() => { consentimentoNaPilha.current = false; });
            fecharCamada(() => composer.confirmarImagens());
          }}
        />
      )}
    </div>
  );
}
