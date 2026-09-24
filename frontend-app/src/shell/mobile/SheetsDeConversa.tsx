/**
 * Folhas de ação sobre conversas: o menu de uma conversa, o "mover para" e o
 * "renomear".
 *
 * Excluir conversa continua fora (decisão D3): não existe no backend, e um botão
 * que não faz nada é pior que botão nenhum. Renomear entrou em 2026-09-24,
 * junto com a rota `PATCH /conversations/{id}`.
 */

import { useState } from 'react';

import { MAX_TITULO_CONVERSA } from '../../api/conversations';
import type { Folder } from '../../api/folders';
import { BottomSheet } from './BottomSheet';
import { Icone } from './Icone';

export function SheetAcoes({ titulo, onRenomear, onMover, onSelecionar, onFechar }: {
  titulo: string;
  onRenomear: () => void;
  onMover: () => void;
  onSelecionar: () => void;
  onFechar: () => void;
}) {
  return (
    <BottomSheet titulo="Ações" onFechar={onFechar}>
      <div className="mv-as-ctx">{titulo}</div>
      <div className="mv-as-lista">
        <button type="button" className="mv-as-i" onClick={onRenomear}><Icone n="edit" />Renomear</button>
        <button type="button" className="mv-as-i" onClick={onMover}><Icone n="move" />Mover para pasta</button>
        <button type="button" className="mv-as-i" onClick={onSelecionar}><Icone n="selsq" />Selecionar</button>
      </div>
    </BottomSheet>
  );
}

export function SheetRenomear({ tituloAtual, onSalvar, onFechar }: {
  tituloAtual: string | null;
  onSalvar: (titulo: string) => void;
  onFechar: () => void;
}) {
  const [titulo, setTitulo] = useState(tituloAtual ?? '');
  const limpo = titulo.replace(/\s+/g, ' ').trim();
  const podeSalvar = limpo.length > 0 && limpo !== (tituloAtual ?? '');
  const salvar = () => { if (podeSalvar) onSalvar(limpo); };

  return (
    <BottomSheet
      titulo="Renomear conversa"
      onFechar={onFechar}
      rodape={
        <button type="button" className="mv-btn mv-btn-pri mv-full" disabled={!podeSalvar} onClick={salvar}>
          Salvar
        </button>
      }
    >
      <label className="mv-fld">
        <span className="mv-fld-l">Título</span>
        <input
          className="mv-inp"
          value={titulo}
          maxLength={MAX_TITULO_CONVERSA}
          onChange={e => setTitulo(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') salvar(); }}
          placeholder="Ex.: Otite — Maria, 6 anos"
          enterKeyHint="done"
        />
      </label>
    </BottomSheet>
  );
}

/** `null` = "Sem pasta" (tira da pasta). */
type Destino = string | null;

export function SheetMover({ quantas, pastas, pastaAtual, onMover, onFechar }: {
  quantas: number;
  pastas: Folder[];
  /** Pasta em que a conversa já está (quando é uma só), para vir marcada. */
  pastaAtual?: string | null;
  onMover: (destino: Destino) => void;
  onFechar: () => void;
}) {
  const [destino, setDestino] = useState<Destino | undefined>(pastaAtual === undefined ? undefined : pastaAtual);
  const nomeDoDestino = destino === undefined ? null : destino === null ? 'Sem pasta' : pastas.find(p => p.id === destino)?.name;
  const titulo = quantas === 1 ? 'Mover conversa' : `Mover ${quantas} conversas`;

  return (
    <BottomSheet
      titulo={titulo}
      onFechar={onFechar}
      rodape={
        <button
          type="button"
          className="mv-btn mv-btn-pri mv-full"
          disabled={destino === undefined || destino === pastaAtual}
          onClick={() => destino !== undefined && onMover(destino)}
        >
          {!nomeDoDestino ? 'Escolha o destino'
            : destino === pastaAtual ? (destino === null ? 'Já está sem pasta' : `Já está em ${nomeDoDestino}`)
            : `Mover para ${nomeDoDestino}`}
        </button>
      }
    >
      <div className="mv-opts" role="radiogroup" aria-label="Destino">
        {pastas.map(p => (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={destino === p.id}
            className={'mv-opt' + (destino === p.id ? ' on' : '')}
            onClick={() => setDestino(p.id)}
          >
            <span className="mv-opt-i"><Icone n="folder" s={20} /></span>
            <span className="mv-opt-t"><b>{p.name}</b></span>
            <span className={'mv-radio' + (destino === p.id ? ' on' : '')} aria-hidden="true" />
          </button>
        ))}
        <button
          type="button"
          role="radio"
          aria-checked={destino === null}
          className={'mv-opt' + (destino === null ? ' on' : '')}
          onClick={() => setDestino(null)}
        >
          <span className="mv-opt-i"><Icone n="x" s={20} /></span>
          <span className="mv-opt-t"><b>Sem pasta</b></span>
          <span className={'mv-radio' + (destino === null ? ' on' : '')} aria-hidden="true" />
        </button>
      </div>
      {pastas.length === 0 && (
        <p className="mv-lede">Você ainda não tem pastas. Crie uma na aba Pastas.</p>
      )}
    </BottomSheet>
  );
}
