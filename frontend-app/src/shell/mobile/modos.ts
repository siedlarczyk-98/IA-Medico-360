/**
 * Os seis modos do orquestrador, como a casca mobile os apresenta.
 *
 * Nome curto (cabe no chip do campo de digitação) e descrição de uma linha
 * (cabe na sheet). As descrições seguem as do `EmptyState` do desktop, e não
 * as do protótipo: lá o Data Ocean aparecia como "análise de planilhas", e ele
 * é consulta a dados OFICIAIS brasileiros — a descrição errada mandaria o
 * médico anexar planilha no modo que não lê planilha.
 */

import type { OrchestratorMode } from '../../components/InputBar';
import type { NomeIcone } from './Icone';

export interface Modo {
  key: OrchestratorMode;
  nome: string;
  /** Rótulo do atalho na tela vazia: uma palavra, para caberem vários na linha. */
  curto: string;
  descricao: string;
  icone: NomeIcone;
}

export const MODOS: Modo[] = [
  { key: 'QUICK_SEARCH',       nome: 'Busca rápida',       curto: 'Busca',         icone: 'bolt',  descricao: 'Resposta direta: posologia, protocolo, critério diagnóstico.' },
  { key: 'CLINICAL_REASONING', nome: 'Raciocínio clínico', curto: 'Clínico',       icone: 'steth', descricao: 'Hipóteses, exames e conduta com base em diretrizes.' },
  { key: 'PHARMA_CHECK',       nome: 'Fármacos',           curto: 'Fármacos',      icone: 'pill',  descricao: 'Interações, bula, receita e genéricos, com dados da ANVISA.' },
  { key: 'EXAM_REVIEW',        nome: 'Exames',             curto: 'Exames',        icone: 'scan',  descricao: 'Anexe laudo, imagem ou resultado — até 5 arquivos.' },
  { key: 'PRODUCTIVITY',       nome: 'Produtividade',      curto: 'Produtividade', icone: 'tasks', descricao: 'Laudos, e-mails, receitas, resumos e tarefas administrativas.' },
  { key: 'DATA_OCEAN',         nome: 'Data Ocean',         curto: 'Data Ocean',    icone: 'db',    descricao: 'Dados oficiais brasileiros: saúde, população, economia.' },
];

export function modo(key: OrchestratorMode): Modo {
  return MODOS.find(m => m.key === key) ?? MODOS[0];
}
