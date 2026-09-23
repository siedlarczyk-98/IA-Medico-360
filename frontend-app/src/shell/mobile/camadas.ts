/**
 * Camadas da casca mobile (gaveta, telas por cima da Consulta, folhas) e o
 * botão VOLTAR.
 *
 * No celular, voltar (o botão do Android, o gesto da borda) é como se fecha
 * alguma coisa. Sem isto, voltar com a gaveta aberta saía do Médico 360 inteiro
 * — dentro do app da Waid, voltava para a tela anterior do hospedeiro, com a
 * conversa perdida de vista.
 *
 * COMO
 * Abrir uma camada empilha uma entrada no histórico do navegador (mesma URL, só
 * o `state` muda: nada de rota nova, o link de embed continua um só). Voltar
 * dispara `popstate`, e ele fecha as camadas que ficaram acima da profundidade
 * da entrada atual. Fechar pela interface (✕, toque fora, Esc) chama
 * `history.back()` — o MESMO caminho, para que histórico e tela nunca
 * discordem.
 *
 * POR QUE NÃO UM EFEITO QUE EMPILHA AO MONTAR
 * `history.back()` é assíncrono. Um efeito que empilha ao montar e volta ao
 * desmontar, sob o StrictMode (monta, desmonta, monta), empilhava de novo
 * ANTES de o `back()` pendente rodar, e o `back()` acabava tirando a entrada
 * nova: a camada fechava sozinha. Aqui empilhar acontece no clique que abre.
 *
 * TROCAR, NÃO FECHAR-E-ABRIR
 * Pelo mesmo motivo, passar de uma camada para outra no mesmo nível (a folha de
 * ações virando a folha "mover para pasta", uma aba virando outra) usa
 * `trocarCamada`: substitui quem fecha o topo, sem mexer no histórico.
 */

type Fechar = () => void;

const pilha: Fechar[] = [];
let ouvindo = false;
/** O que fazer depois que o `popstate` pedido por `fecharCamada` chegar. */
let depoisDeVoltar: (() => void) | null = null;
const CHAVE = 'mvCamada';

function profundidadeDoEstado(estado: unknown): number {
  if (estado && typeof estado === 'object' && CHAVE in estado) {
    const n = (estado as Record<string, unknown>)[CHAVE];
    return typeof n === 'number' ? n : 0;
  }
  return 0;
}

function aoVoltar(e: PopStateEvent) {
  // `history.go(-n)` dispara UM popstate só: fecha tudo acima do nível novo.
  const alvo = profundidadeDoEstado(e.state);
  while (pilha.length > alvo) pilha.pop()?.();
  const depois = depoisDeVoltar;
  depoisDeVoltar = null;
  depois?.();
}

function ouvir() {
  if (ouvindo) return;
  window.addEventListener('popstate', aoVoltar);
  ouvindo = true;
}

/** Abre uma camada. `fechar` é chamado quando o médico volta (ou a interface fecha). */
export function abrirCamada(fechar: Fechar): void {
  ouvir();
  pilha.push(fechar);
  // Preserva o `state` do roteador (chave e índice) e só acrescenta a profundidade.
  const atual = (window.history.state ?? {}) as Record<string, unknown>;
  window.history.pushState({ ...atual, [CHAVE]: pilha.length }, '');
}

/**
 * Fecha a camada de cima pelo mesmo caminho do botão voltar.
 *
 * `depois` roda quando a volta tiver acontecido. É o jeito de "fechar esta e
 * abrir aquela" (a folha de ações que leva ao modo de seleção): abrir antes
 * empilharia uma entrada que o `back()` pendente tiraria em seguida.
 */
export function fecharCamada(depois?: () => void): void {
  if (pilha.length === 0) {
    depois?.();
    return;
  }
  depoisDeVoltar = depois ?? null;
  window.history.back();
}

/**
 * Volta até sobrarem `profundidade` camadas e então roda `depois`.
 *
 * Trocar de aba com uma pasta aberta por cima: primeiro desce até o nível da
 * aba, depois troca. Trocar direto substituiria o fecho da PASTA, e ela ficaria
 * na tela com o histórico do navegador já dizendo outra coisa.
 */
export function voltarPara(profundidade: number, depois?: () => void): void {
  if (pilha.length <= profundidade) {
    depois?.();
    return;
  }
  depoisDeVoltar = depois ?? null;
  window.history.go(profundidade - pilha.length);
}

/** Fecha todas as camadas (ex.: escolheu uma conversa lá no fundo da gaveta). */
export function fecharTodasCamadas(): void {
  voltarPara(0);
}

/** Troca quem fecha a camada de cima, sem tocar no histórico. */
export function trocarCamada(fechar: Fechar): void {
  if (pilha.length === 0) {
    abrirCamada(fechar);
    return;
  }
  pilha[pilha.length - 1] = fechar;
}

export function haCamadaAberta(): boolean {
  return pilha.length > 0;
}

/** Só para testes: a pilha é de módulo e vazaria de um teste para o outro. */
export function reiniciarCamadas(): void {
  pilha.length = 0;
  depoisDeVoltar = null;
}
