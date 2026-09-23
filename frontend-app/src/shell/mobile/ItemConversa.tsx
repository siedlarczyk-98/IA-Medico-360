/**
 * Uma conversa na lista do celular: título, hora e (se houver) a pasta.
 *
 * As ações ficam no "…" E no toque longo. No desktop elas aparecem no hover,
 * que não existe no dedo; e arrastar para uma pasta, que o desktop usa, não
 * funciona no toque. Aqui mover é pelo menu.
 */

import { memo, useRef } from 'react';

import type { ConversationSummary } from '../../api/conversations';
import { quando, tituloDe } from './agruparConversas';
import { Icone } from './Icone';

/** Tempo de dedo parado que conta como toque longo. */
const TOQUE_LONGO_MS = 500;

interface Props {
  conversa: ConversationSummary;
  nomeDaPasta?: string;
  ativa: boolean;
  /** Modo seleção: o toque marca/desmarca em vez de abrir. */
  selecionando: boolean;
  selecionada: boolean;
  onAbrir: (id: string) => void;
  onAcoes: (c: ConversationSummary) => void;
  onAlternar: (id: string) => void;
}

export const ItemConversa = memo(function ItemConversa({
  conversa, nomeDaPasta, ativa, selecionando, selecionada, onAbrir, onAcoes, onAlternar,
}: Props) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const disparou = useRef(false);

  function cancelar() {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }

  const titulo = tituloDe(conversa);

  return (
    <div className={'mv-li' + (selecionada ? ' sel' : '') + (ativa && !selecionando ? ' ativa' : '')}>
      <button
        type="button"
        className="mv-li-principal"
        aria-pressed={selecionando ? selecionada : undefined}
        onPointerDown={() => {
          if (selecionando) return;
          disparou.current = false;
          cancelar();
          timer.current = setTimeout(() => {
            disparou.current = true;
            onAcoes(conversa);
          }, TOQUE_LONGO_MS);
        }}
        onPointerUp={cancelar}
        onPointerLeave={cancelar}
        onPointerCancel={cancelar}
        // O Android abre o menu do navegador no toque longo; o nosso vale mais.
        onContextMenu={e => e.preventDefault()}
        onClick={() => {
          if (disparou.current) { disparou.current = false; return; }
          if (selecionando) onAlternar(conversa.id);
          else onAbrir(conversa.id);
        }}
      >
        {selecionando && (
          <span className={'mv-ck' + (selecionada ? ' on' : '')} aria-hidden="true">
            {selecionada && <Icone n="check" s={14} w={3} />}
          </span>
        )}
        <span className="mv-li-t">
          <b>{titulo}</b>
          <span className="mv-li-m">
            <span>{quando(conversa.updated_at)}</span>
            {nomeDaPasta && <><span aria-hidden="true">·</span><span className="mv-li-pasta"><Icone n="folder" s={14} w={2} />{nomeDaPasta}</span></>}
          </span>
        </span>
      </button>
      {!selecionando && (
        <button type="button" className="mv-ib" aria-label={`Ações: ${titulo}`} onClick={() => onAcoes(conversa)}>
          <Icone n="more" s={20} />
        </button>
      )}
    </div>
  );
});
