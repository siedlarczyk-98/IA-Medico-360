/** "Ana Beatriz Moura" → "AB". O avatar da casca mobile não tem foto. */
export function iniciais(nome: string | null | undefined): string {
  return (nome ?? '').split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]?.toUpperCase()).join('') || '·';
}
