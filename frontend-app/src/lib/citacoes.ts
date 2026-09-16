/**
 * Normalização das fontes citadas.
 *
 * POR QUE DOIS FORMATOS
 * ---------------------
 * O campo `citations` nasceu como `list[str]` — só a URL. Passou a carregar
 * também o título do artigo, que os provedores de busca (Anthropic, OpenAI,
 * Google, Perplexity) sempre enviaram e o backend descartava na extração.
 *
 * As conversas gravadas antes dessa mudança continuam no JSONB como lista de
 * strings, e **não há backfill** — buscar o título de cada URL antiga exigiria
 * uma requisição por fonte contra sites que podem ter saído do ar. Então este
 * módulo aceita os dois formatos para sempre, não como transição.
 *
 * O que a tela mostra em cada caso foi decidido pelo usuário em 2026-09-16:
 * conversa nova mostra só o título; conversa antiga, sem título, mostra o
 * domínio (`pubmed.ncbi.nlm.nih.gov`) em vez da URL inteira.
 */

/** Uma fonte como pode chegar do backend: URL crua (legado) ou objeto. */
export type CitacaoBruta = string | { url: string; title?: string | null };

export type Citacao = {
  url: string
  /** O que a tela mostra: título quando há, domínio quando não. */
  rotulo: string
  /** `false` quando o rótulo é domínio derivado, não título de verdade. */
  temTitulo: boolean
}

/**
 * `https://pubmed.ncbi.nlm.nih.gov/42661420/` → `pubmed.ncbi.nlm.nih.gov`.
 *
 * O `www.` sai porque não distingue nada e só gasta espaço numa lista onde o
 * domínio já é o plano B. Se a URL for inválida (veio torta do banco), devolve
 * a string original: melhor mostrar algo estranho que engolir a fonte.
 */
export function dominioDe(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/**
 * Título vazio ou só espaço é tratado como ausente — provedor às vezes manda
 * `""`, e um item de lista em branco é pior que o domínio.
 */
export function normalizarCitacoes(brutas: readonly CitacaoBruta[]): Citacao[] {
  return brutas.map((bruta) => {
    if (typeof bruta === 'string') {
      return { url: bruta, rotulo: dominioDe(bruta), temTitulo: false }
    }
    const titulo = bruta.title?.trim()
    return titulo
      ? { url: bruta.url, rotulo: titulo, temTitulo: true }
      : { url: bruta.url, rotulo: dominioDe(bruta.url), temTitulo: false }
  })
}
