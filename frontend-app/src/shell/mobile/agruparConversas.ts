/**
 * Histórico do celular agrupado por data, com TODAS as conversas.
 *
 * O `groupByDate` da sidebar tira as conversas que estão em pastas, porque lá
 * as pastas ficam na mesma coluna, logo acima. No celular Histórico e Pastas
 * são telas separadas: tirar as conversas de pasta do Histórico faria a
 * conversa de ontem "sumir" para quem não lembra em que pasta a pôs. Aqui elas
 * aparecem, com o nome da pasta na linha.
 */

import type { ConversationSummary } from '../../api/conversations';

export interface GrupoDeConversas {
  rotulo: string;
  itens: ConversationSummary[];
}

const DIA = 24 * 60 * 60 * 1000;
const DIAS_DA_SEMANA = ['dom.', 'seg.', 'ter.', 'qua.', 'qui.', 'sex.', 'sáb.'];
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

function inicioDoDia(d: Date): number {
  const c = new Date(d);
  c.setHours(0, 0, 0, 0);
  return c.getTime();
}

export function agruparConversas(conversas: ConversationSummary[], agora = new Date()): GrupoDeConversas[] {
  const hoje = inicioDoDia(agora);
  const grupos: GrupoDeConversas[] = [
    { rotulo: 'Hoje', itens: [] },
    { rotulo: 'Ontem', itens: [] },
    { rotulo: 'Últimos 7 dias', itens: [] },
    { rotulo: 'Mais antigas', itens: [] },
  ];
  const ordenadas = [...conversas].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  for (const c of ordenadas) {
    const dia = inicioDoDia(new Date(c.updated_at));
    if (dia >= hoje) grupos[0].itens.push(c);
    else if (dia >= hoje - DIA) grupos[1].itens.push(c);
    else if (dia >= hoje - 7 * DIA) grupos[2].itens.push(c);
    else grupos[3].itens.push(c);
  }
  return grupos.filter(g => g.itens.length > 0);
}

/** "14:12" hoje e ontem, "seg., 21/set" na semana, "12/set" antes disso. */
export function quando(iso: string, agora = new Date()): string {
  const d = new Date(iso);
  const hoje = inicioDoDia(agora);
  const dia = inicioDoDia(d);
  const dd = String(d.getDate()).padStart(2, '0');
  if (dia >= hoje - DIA) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
  if (dia >= hoje - 7 * DIA) return `${DIAS_DA_SEMANA[d.getDay()]}, ${dd}/${MESES[d.getMonth()]}`;
  const ano = d.getFullYear() !== agora.getFullYear() ? `/${d.getFullYear()}` : '';
  return `${dd}/${MESES[d.getMonth()]}${ano}`;
}

/** Título de uma conversa sem título: melhor dizer isso do que mostrar vazio. */
export function tituloDe(c: ConversationSummary): string {
  return c.title?.trim() || 'Conversa sem título';
}
