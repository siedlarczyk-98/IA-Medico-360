/**
 * Onde a casca mobile está rodando: dentro da Waid, ou sozinha no navegador.
 *
 * Não é a mesma pergunta de `layout.ts` (desktop ou mobile). Esta decide a
 * NAVEGAÇÃO dentro da casca mobile:
 *
 * - `hospedado` — app nativo da Waid (webview com a ponte `ReactNativeWebView`)
 *   ou o site da Waid (iframe). Nos dois, a Waid já desenha cabeçalho com a
 *   marca e uma barra de abas própria em volta de nós. Uma segunda barra de
 *   abas empilhada confunde e rouba ~110 px de uma área que no Android pequeno
 *   mal passa de 600 px. Aqui: cabeçalho de uma linha (☰ · título · nova
 *   consulta) e gaveta, sem logo.
 * - `avulso` — URL aberta direto no navegador. Nada em volta: logo no
 *   cabeçalho, e (nas próximas fases) barra de abas embaixo.
 *
 * Decidido pelo canal que existe, nunca por parâmetro na URL: a Waid tem um
 * link só, o mesmo para o app e para o site.
 */

import { temIframe, temPonteNativa } from '@shared/embed/identidade';

export type Hospedeiro = 'hospedado' | 'avulso';

export function detectarHospedeiro(): Hospedeiro {
  return temPonteNativa() || temIframe() ? 'hospedado' : 'avulso';
}
