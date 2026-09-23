/**
 * Criar ou editar uma pasta, numa folha.
 *
 * Mesmas regras do `FolderModal` do desktop (`useFormularioPasta`): a pergunta
 * "é sobre um paciente?" vem primeiro porque muda o rótulo e o exemplo do campo
 * de contexto, e o contexto é opcional e dito como tal.
 *
 * Excluir fica aqui dentro, com confirmação: é destrutivo e raro, e não merece
 * um lugar de destaque na tela da pasta.
 */

import { useState } from 'react';

import { MAX_CHARS_EVOLUCAO, type Folder, type FolderKind } from '../../api/folders';
import { useFormularioPasta } from '../../hooks/useFormularioPasta';
import { BottomSheet } from './BottomSheet';

interface Props {
  pasta?: Folder;
  onSalvar: (name: string, clinicalContext: string, folderKind: FolderKind) => void;
  onExcluir?: () => void;
  onFechar: () => void;
}

export function SheetPasta({ pasta, onSalvar, onExcluir, onFechar }: Props) {
  const f = useFormularioPasta(pasta, onSalvar);
  const [confirmandoExclusao, setConfirmandoExclusao] = useState(false);

  return (
    <BottomSheet
      titulo={f.editando ? 'Editar pasta' : 'Nova pasta'}
      onFechar={onFechar}
      rodape={
        <button type="button" className="mv-btn mv-btn-pri mv-full" disabled={!f.podeSalvar} onClick={f.salvar}>
          {f.editando ? 'Salvar' : 'Criar pasta'}
        </button>
      }
    >
      <div className="mv-fld">
        <span className="mv-fld-l" id="mv-tipo-pasta">Esta pasta é sobre um paciente?</span>
        <div className="mv-seg" role="radiogroup" aria-labelledby="mv-tipo-pasta">
          {([
            ['clinical', 'Sim, é clínica', 'Um paciente'],
            ['general', 'Não', 'Estudo ou tema'],
          ] as const).map(([kind, nome, detalhe]) => (
            <button
              key={kind}
              type="button"
              role="radio"
              aria-checked={f.folderKind === kind}
              className={f.folderKind === kind ? 'on' : undefined}
              onClick={() => f.setFolderKind(kind)}
            >
              {nome}<small>{detalhe}</small>
            </button>
          ))}
        </div>
      </div>

      <label className="mv-fld">
        <span className="mv-fld-l">Nome</span>
        <input
          className="mv-inp"
          value={f.name}
          onChange={e => f.setName(e.target.value)}
          placeholder="Ex.: Paciente Jorge, ou Cardiologia"
        />
      </label>

      <label className="mv-fld">
        <span className="mv-fld-l">{f.textos.rotulo} <span className="mv-opcional">(opcional)</span></span>
        <textarea
          className="mv-inp mv-inp-area"
          value={f.clinicalContext}
          onChange={e => f.setClinicalContext(e.target.value)}
          placeholder={f.textos.placeholder}
          rows={5}
        />
        <small>{f.textos.ajuda}</small>
        <small className={f.excedeu ? 'mv-erro' : undefined}>
          {f.clinicalContext.length.toLocaleString('pt-BR')} / {MAX_CHARS_EVOLUCAO.toLocaleString('pt-BR')}
          {f.excedeu && ' — acima do limite. Resuma o essencial do caso.'}
        </small>
      </label>

      {f.editando && onExcluir && (
        confirmandoExclusao ? (
          <div className="mv-perigo" role="alert">
            <p>Excluir a pasta? As conversas dela continuam no Histórico, sem pasta.</p>
            <div className="mv-perigo-acoes">
              <button type="button" className="mv-btn mv-btn-sec" onClick={() => setConfirmandoExclusao(false)}>Cancelar</button>
              <button type="button" className="mv-btn mv-btn-perigo" onClick={onExcluir}>Excluir pasta</button>
            </div>
          </div>
        ) : (
          <button type="button" className="mv-btn-texto mv-btn-texto-perigo" onClick={() => setConfirmandoExclusao(true)}>
            Excluir pasta
          </button>
        )
      )}
    </BottomSheet>
  );
}
