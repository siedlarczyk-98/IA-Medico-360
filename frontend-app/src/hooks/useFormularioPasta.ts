/**
 * Estado e validação do formulário de pasta (criar e editar).
 *
 * O `FolderModal` do desktop e a sheet da casca mobile desenham o formulário
 * de jeitos diferentes; a regra do que pode ser salvo é uma só. Os textos por
 * tipo moram aqui pelo mesmo motivo: "evolução do paciente" numa pasta de
 * estudos não pode voltar a aparecer em uma das cascas.
 */

import { useState } from 'react';

import { MAX_CHARS_EVOLUCAO, type Folder, type FolderKind } from '../api/folders';

export function useFormularioPasta(
  folder: Folder | undefined,
  onSave: (name: string, clinicalContext: string, folderKind: FolderKind) => void,
  saving = false,
) {
  const [name, setName] = useState(folder?.name ?? '');
  const [clinicalContext, setClinicalContext] = useState(folder?.clinical_context ?? '');
  const [folderKind, setFolderKind] = useState<FolderKind>(folder?.folder_kind ?? 'clinical');

  const excedeu = clinicalContext.length > MAX_CHARS_EVOLUCAO;
  const podeSalvar = name.trim().length > 0 && !excedeu && !saving;

  function salvar() {
    if (!podeSalvar) return;
    onSave(name.trim(), clinicalContext.trim(), folderKind);
  }

  return {
    editando: folder !== undefined,
    name, setName,
    clinicalContext, setClinicalContext,
    folderKind, setFolderKind,
    textos: TEXTOS_POR_TIPO[folderKind],
    excedeu,
    podeSalvar,
    salvar,
  };
}

/**
 * Rótulo, exemplo e explicação por tipo de pasta.
 *
 * O campo é o mesmo (uma coluna só no banco), mas chamá-lo de "evolução do
 * paciente" numa pasta de estudos não significa nada — foi o que motivou a
 * pergunta no topo da tela. O texto de ajuda também muda: numa pasta clínica o
 * ganho é não repetir o caso; numa geral, é não repetir o objetivo.
 */
export const TEXTOS_POR_TIPO: Record<FolderKind, { rotulo: string; placeholder: string; ajuda: string }> = {
  clinical: {
    rotulo: 'Evolução do paciente',
    placeholder:
      'Ex.: Jorge, 58a, HAS + DM2 há 8 anos.\nLosartana 50mg 12/12h, metformina 850mg.\nAlergia a dipirona.\nÚltima consulta: PA 150/95, HbA1c 8.2.',
    ajuda:
      'Se preenchida, é considerada em todas as conversas desta pasta — sem que você precise repetir o caso a cada pergunta. Pode editar quando o quadro mudar.',
  },
  general: {
    rotulo: 'Contexto da pasta',
    placeholder:
      'Ex.: Revisão para prova de título em cardiologia.\nFoco em arritmias e insuficiência cardíaca.\nPreferência por respostas com referência a guidelines.',
    ajuda:
      'Se preenchido, é considerado em todas as conversas desta pasta — sem que você precise repetir o objetivo a cada pergunta. Pode editar quando quiser.',
  },
};
