/**
 * Transforma marcadores de citação `[1]` em superscrito, no componente de
 * parágrafo/lista do react-markdown.
 *
 * O PROBLEMA
 * ----------
 * O prompt manda o modelo numerar as citações (`app/core/prompts.py`), e ele
 * escreve `[1]`, `[10]` colados no fim da frase. Isso chega ao markdown como
 * texto literal — `[1]` sozinho não é sintaxe de link, então o react-markdown
 * o renderiza no corpo do texto, no mesmo tamanho e peso da frase. Em bullets
 * curtos vira `...tratamento de base.[1][10]`, que compete com a palavra que
 * deveria estar marcando.
 *
 * POR QUE NÃO UM PLUGIN REMARK
 * ----------------------------
 * Um plugin que visita a árvore seria mais elegante e evitaria tocar em código
 * inline sem ajuda. Mas exigiria `unist-util-visit`, que hoje só existe em
 * `node_modules` como dependência TRANSITIVA do react-markdown — importá-la
 * sem declarar no `package.json` funciona até o dia em que o react-markdown
 * trocar de versão ou de árvore de dependências, e aí quebra o build sem que
 * ninguém tenha mexido neste arquivo.
 *
 * Então a transformação acontece nos nós de texto que o react-markdown já
 * entrega prontos aos componentes: `children` de um `<p>` ou `<li>` é um array
 * onde código, links e ênfases já são ELEMENTOS React, e só o texto solto é
 * string. Transformar apenas as strings dá, de graça, a mesma imunidade que o
 * plugin daria — um `[0]` dentro de bloco de código nunca chega aqui como
 * string solta.
 *
 * O superscrito é só estilo: o número continua sendo texto, legível por leitor
 * de tela e selecionável. Não vira link para a lista de Fontes de propósito —
 * a numeração que o modelo escreve e a da seção "Fontes" são geradas por
 * mecanismos independentes e podem não corresponder.
 */

import { Fragment, isValidElement, type ReactNode } from 'react'

/**
 * Um marcador: `[1]`, `[10]`, `[999]`.
 *
 * Limitado a 1-3 dígitos para não capturar `[2026]`, que numa resposta médica
 * é quase sempre um ano, não uma citação.
 */
const MARCADOR = /\[(\d{1,3})\]/g

const estiloSup: React.CSSProperties = {
  fontSize: '0.72em',
  lineHeight: 0,
  verticalAlign: 'super',
  color: 'var(--pen3)',
  fontWeight: 600,
  // Separa `[1][10]` sem espaço de texto real, que o leitor de tela anunciaria.
  marginLeft: 1,
}

/** Quebra uma string em texto + `<sup>`, preservando tudo que não for marcador. */
function transformarTexto(texto: string, chaveBase: string): ReactNode[] | null {
  // `matchAll` não sofre do estado global de `lastIndex` que `test`/`exec`
  // carregam num regex com flag `g` reutilizado entre chamadas.
  const achados = [...texto.matchAll(MARCADOR)]
  if (achados.length === 0) return null

  const partes: ReactNode[] = []
  let cursor = 0

  achados.forEach((achado, i) => {
    const inicio = achado.index
    if (inicio > cursor) partes.push(texto.slice(cursor, inicio))
    partes.push(
      <sup key={`${chaveBase}-${i}`} style={estiloSup}>
        {achado[1]}
      </sup>,
    )
    cursor = inicio + achado[0].length
  })

  if (cursor < texto.length) partes.push(texto.slice(cursor))
  return partes
}

/**
 * Aplica a transformação nos filhos de um nó de markdown.
 *
 * Desce em elementos React para pegar texto dentro de `<strong>`/`<em>` — o
 * modelo escreve `**negrito**[1]` e às vezes `**negrito[1]**`. Não desce em
 * elementos sem `children` (imagens) nem em código/link, que o react-markdown
 * já entregou como elemento próprio.
 */
export function comMarcadoresDeCitacao(children: ReactNode, chaveBase = 'c'): ReactNode {
  if (typeof children === 'string') {
    return transformarTexto(children, chaveBase) ?? children
  }

  if (Array.isArray(children)) {
    return children.map((filho, i) => (
      <Fragment key={i}>{comMarcadoresDeCitacao(filho, `${chaveBase}-${i}`)}</Fragment>
    ))
  }

  if (isValidElement<{ children?: ReactNode }>(children)) {
    const tipo = children.type
    // `code` e `a` chegam como elemento; o texto dentro deles não é citação.
    if (tipo === 'code' || tipo === 'a') return children

    const netos = children.props.children
    if (netos === undefined) return children
    return {
      ...children,
      props: { ...children.props, children: comMarcadoresDeCitacao(netos, chaveBase) },
    }
  }

  return children
}
