import type { ConversationSummary } from '../../api/conversations';

export function groupByDate(conversations: ConversationSummary[]) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);

  const groups: { label: string; items: ConversationSummary[] }[] = [
    { label: 'Hoje', items: [] },
    { label: 'Esta semana', items: [] },
    { label: 'Anteriores', items: [] },
  ];

  for (const conv of conversations) {
    if (conv.folder_id) continue; // pastas tratadas separadamente
    const d = new Date(conv.updated_at);
    d.setHours(0, 0, 0, 0);
    if (d >= today) groups[0].items.push(conv);
    else if (d >= weekAgo) groups[1].items.push(conv);
    else groups[2].items.push(conv);
  }

  return groups.filter(g => g.items.length > 0);
}
