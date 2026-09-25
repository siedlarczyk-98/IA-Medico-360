/**
 * Handshake de identidade com a Waid, dentro do iframe do LMS.
 *
 * POR QUE ISTO EXISTE
 * Até aqui a identidade vinha como `?email=` na URL do iframe. Isso não prova
 * nada: quem soubesse o e-mail de um colega recebia a sessão dele, porque o
 * header `Origin` é forjável server-side e a validação de matrícula só confirma
 * que o e-mail É de um membro — não que o chamador É ele.
 *
 * A Waid passou a emitir um token opaco, de uso único, válido por 5 minutos,
 * entregue por `postMessage` a quem está de fato dentro do iframe, logado. O
 * token não carrega informação: o backend o troca pela identidade numa chamada
 * server-to-server. **O e-mail virou resultado da verificação, não entrada.**
 *
 * Escrito em `shared/` desde o primeiro app: os dois `EmbedAuthPage.tsx` são
 * byte a byte idênticos exceto pelo destino da navegação, e o `noticias-app`
 * repete a mesma lógica inline. Escrever dentro de um app e mover depois seria
 * recriar de propósito a duplicação que a migração vai desfazer.
 *
 * Referência: doc "Identidade do aluno em seção incorporada — Waid", v1.2.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

/** Intervalo de reenvio do pedido, conforme a doc. */
const INTERVALO_PEDIDO_MS = 2000;

/** Desiste depois disto e mostra erro com saída para o login. */
const TIMEOUT_MS = 30_000;

/**
 * Quantas vezes vale retentar quando o token queima antes da troca. Acontece
 * de verdade (recarregar a página invalida o token em voo); mais que isto
 * indica outro problema, e insistir só empurra o diagnóstico para frente.
 */
const MAX_TENTATIVAS = 3;

/**
 * Esperas antes de repetir a troca quando o servidor responde 429.
 *
 * Num evento, dezenas de médicos abrem o app ao mesmo tempo atrás do mesmo IP,
 * e o limite por IP de `/auth/embed/token` pode estourar por segundos. Desistir
 * ali mandava o médico para o login por código — que tem limite menor ainda.
 * Repetir com o MESMO token é seguro: o limitador recusa antes de a rota rodar,
 * então o token de uso único da Waid não foi gasto.
 *
 * Esperas fixas, e não o `Retry-After`: o cabeçalho não chega ao JavaScript
 * (o CORS não o expõe e o limitador não o emite). O sorteio em cima de cada
 * espera evita que os aparelhos barrados juntos voltem juntos.
 */
const ESPERAS_NO_LIMITE_MS = [2000, 5000, 10_000];

function esperarNoLimite(ms: number): Promise<void> {
  const sorteio = Math.random() * 1000;
  return new Promise(resolve => setTimeout(resolve, ms + sorteio));
}

/** Faz a chamada e, a cada 429, espera e repete — até esgotar as esperas. */
async function comEsperaNoLimite(chamar: () => Promise<Response>): Promise<Response> {
  let resp = await chamar();
  for (const espera of ESPERAS_NO_LIMITE_MS) {
    if (resp.status !== 429) break;
    await esperarNoLimite(espera);
    resp = await chamar();
  }
  return resp;
}

/**
 * Origem que os aplicativos nativos da Waid usam ao entregar a identidade.
 *
 * Medido em 22/09/2026 no app 1.58.9: a ponte responde a partir de
 * `https://www.medico360.app`, e não do portal (`adminportalmedico360...`)
 * que o `VITE_WAID_ORIGIN` aponta para o caso do navegador. As duas são
 * legítimas e coexistem — por isso uma lista, não uma troca.
 *
 * Configurável por env para não exigir deploy de código se a plataforma mudar
 * de domínio; o default cobre o comportamento observado.
 */
export const ORIGEM_APP_NATIVO_WAID = 'https://www.medico360.app';

/**
 * Monta a lista de origens aceitas a partir da origem configurada do portal.
 *
 * Central, e não repetida em cada app: são três `EmbedAuthPage` que precisam
 * da MESMA lista, e foi justamente a divergência silenciosa entre contextos
 * que manteve o app nativo quebrado.
 */
export function montarOrigensWaid(
  origemPortal: string,
  origemApp: string = ORIGEM_APP_NATIVO_WAID,
): string[] {
  return Array.from(new Set([origemPortal, origemApp].filter(Boolean)));
}

export type FaseIdentidade = 'pedindo' | 'trocando' | 'pronto' | 'erro';

export interface MotivoErro {
  /**
   * `sem_iframe`    — a página não está incorporada; ninguém pode responder
   * `timeout`       — está incorporada, mas a Waid não respondeu
   * `indisponivel`  — a troca do token falhou por problema de configuração/rede
   * `recusado`      — a Waid confirmou quem é, e o NOSSO lado recusou (conta
   *                   desativada, identidade vinculada a outra pessoa). A
   *                   `mensagem` vem do servidor e diz o que fazer.
   */
  tipo: 'sem_iframe' | 'timeout' | 'indisponivel' | 'recusado' | 'desconhecido';
  mensagem: string;
}

export interface RespostaSessao {
  access_token: string;
  onboarding_complete: boolean;
}

interface Opcoes {
  apiBase: string;
  /**
   * Origem(ns) da Waid: destino do pedido e origens aceitas na resposta.
   *
   * Aceita lista porque há dois contextos legítimos — o portal no navegador e
   * o domínio público que o app nativo usa. Ver `montarOrigensWaid`.
   */
  waidOrigin: string | string[];
  /** Chamado com a resposta do backend quando a sessão é criada. */
  aoAutenticar: (resposta: RespostaSessao) => void;
}

interface OpcoesIdentidade {
  apiBase: string;
  waidOrigin: string | string[];
  /** Chamado com o nome e o e-mail — sem sessão, sem usuário criado. */
  aoIdentificar: (identidade: IdentidadeSimples) => void;
}

/** O que as landing pages precisam: só para pré-preencher o formulário. */
export interface IdentidadeSimples {
  nome: string | null;
  email: string;
}

interface Estado {
  fase: FaseIdentidade;
  erro: MotivoErro | null;
}

type ResultadoTroca = 'ok' | 'renovar' | 'desistir' | { recusado: string };

/**
 * Recusa com frase para o médico: o 403 que traz `{codigo, mensagem}`.
 *
 * Sem isto, conta desativada e identidade divergente viravam "a verificação
 * está indisponível no momento" — o médico esperava, tentava de novo, e nada
 * mudava. O código é a marca de que a frase é para ser lida; o 403 de origem
 * não autorizada (configuração nossa) não tem código e segue genérico.
 */
function recusaComMensagem(corpo: unknown): string | null {
  const detail = (corpo as { detail?: { codigo?: unknown; mensagem?: unknown } })?.detail;
  if (typeof detail?.codigo !== 'string' || typeof detail.mensagem !== 'string') return null;
  return detail.mensagem;
}

/** Erro que o backend devolve quando o token queimou — dá para pedir outro. */
function tokenPrecisaSerRenovado(corpo: unknown): boolean {
  const detail = (corpo as { detail?: { codigo?: string } })?.detail;
  return detail?.codigo === 'token_invalido' || detail?.codigo === 'token_expirado';
}

/**
 * Pede a identidade à Waid e troca o token por uma sessão nossa.
 *
 * A ordem das operações não é estilo, é requisito da doc:
 *
 *  1. o ouvinte é registrado ANTES do primeiro pedido — uma mensagem que chega
 *     sem ouvinte é perdida, não fica em fila nem é reenviada;
 *  2. o pedido é repetido a cada 2s até a resposta chegar — a ordem de
 *     carregamento varia entre navegadores e o app da Waid, e um pedido sem
 *     resposta não emite token nenhum, então repetir não custa;
 *  3. `event.origin` é conferido. A doc chama isso de opcional; aqui não é —
 *     é a única barreira contra outra janela injetar um token que não é nosso.
 */
/**
 * Existe alguém para responder?
 *
 * Há DOIS jeitos de a Waid nos entregar identidade, e por muito tempo só
 * conhecíamos um:
 *
 *  1. **iframe** (navegador): `window.parent !== window`, e a resposta chega
 *     por `postMessage` do pai;
 *  2. **webview do app nativo**: NÃO há iframe — `window.parent === window` —
 *     e a ponte injeta a mensagem direto na nossa janela. Ela se anuncia em
 *     `window.ReactNativeWebView` / `window.__waidIdentityBridgeInstalled`.
 *
 * O código antigo só previa (1) e abortava com `sem_iframe` em (2). O
 * comentário anterior registrava a medição de setembro/2026 — "eles abrem num
 * webview direto, sem iframe" — como se fosse veredito permanente. Era
 * verdade sobre a versão do app de então; a ponte entrou na 1.57.24 da
 * plataforma. Medido de novo em 22/09/2026, no app 1.58.9 (Android), a página
 * de diagnóstico recebeu `waid:identity` com token **sem estar em iframe**.
 *
 * Por isso a pergunta deixou de ser "estou num iframe?" e passou a ser "existe
 * algum canal por onde a resposta possa chegar?".
 */
interface JanelaComPonte {
  ReactNativeWebView?: unknown;
  __waidIdentityBridgeInstalled?: unknown;
}

export function temIframe(): boolean {
  try {
    return window.parent !== window;
  } catch {
    // Acesso a `window.parent` pode lançar em contexto restrito — se lançou, há
    // um pai de outra origem, então estamos incorporados.
    return true;
  }
}

/** A ponte do app nativo está instalada nesta janela? */
export function temPonteNativa(): boolean {
  try {
    const w = window as unknown as JanelaComPonte;
    return Boolean(w.ReactNativeWebView) || Boolean(w.__waidIdentityBridgeInstalled);
  } catch {
    return false;
  }
}

/**
 * Só desistimos quando não há NENHUM canal possível — nem pai, nem ponte.
 *
 * Note que isto é deliberadamente otimista com a ponte: se ela existe mas não
 * responde, caímos no timeout de 30s com mensagem própria, em vez de negar
 * atendimento a quem talvez pudesse ser atendido. Errar para o lado de esperar
 * é barato; errar para o lado de abortar foi o que manteve o app quebrado.
 */
function podeReceberIdentidade(): boolean {
  return temIframe() || temPonteNativa();
}

/**
 * O handshake em si, sem opinião sobre o que fazer com o token.
 *
 * `trocar` recebe o token e devolve o que deve acontecer:
 *   `ok`       — deu certo, para de pedir
 *   `renovar`  — o token queimou; pede outro (ocorrência normal)
 *   `desistir` — falha que retentar não conserta
 *
 * Existe separado porque há dois usos com necessidades diferentes: os três apps
 * trocam o token por uma SESSÃO; as landing pages, que são públicas, trocam
 * apenas por nome e e-mail para pré-preencher um formulário. O handshake — a
 * ordem, a retentativa, o teto de espera — é idêntico nos dois, e é justamente
 * a parte cheia de detalhe que não pode divergir.
 */
function useHandshakeWaid(
  waidOrigin: string | string[],
  trocar: (token: string) => Promise<ResultadoTroca>,
): Estado {
  // Normaliza para lista uma vez só. `useState` com inicializador, e não um
  // `const` no corpo: um array novo a cada render trocaria a identidade da
  // dependência do efeito e o remontaria no meio do handshake — removendo o
  // ouvinte exatamente enquanto a resposta pode estar chegando.
  const [origens] = useState(() =>
    (Array.isArray(waidOrigin) ? waidOrigin : [waidOrigin]).filter(Boolean),
  );

  const [estado, setEstado] = useState<Estado>(() =>
    podeReceberIdentidade()
      ? { fase: 'pedindo', erro: null }
      : {
          fase: 'erro',
          erro: {
            tipo: 'sem_iframe',
            mensagem: 'Esta tela precisa ser aberta pelo menu da plataforma.',
          },
        },
  );

  // Refs, e não estado: mudanças aqui não devem re-renderizar nem recriar o
  // efeito — recriá-lo removeria o ouvinte no meio do handshake.
  const concluido = useRef(false);
  const tentativas = useRef(0);
  const trocarRef = useRef(trocar);
  trocarRef.current = trocar;

  useEffect(() => {
    // Sem nenhum canal (nem pai, nem ponte nativa) não há handshake possível:
    // não adianta registrar ouvinte nem gastar 30s de espera. O estado inicial
    // já reflete isso.
    if (!podeReceberIdentidade()) return;

    let vivo = true;

    async function aoReceber(event: MessageEvent) {
      // A origem continua sendo conferida — é a única barreira contra outra
      // janela injetar um token que não é nosso. O que mudou é que há mais de
      // uma origem legítima: o embed no navegador vem do portal da Waid, e o
      // app nativo entrega a partir do domínio público da plataforma.
      if (!origens.includes(event.origin)) return;
      if ((event.data as { type?: string })?.type !== 'waid:identity') return;
      if (concluido.current || !vivo) return;

      const token = (event.data as { token?: string }).token;
      if (!token) return;

      // Marca antes da chamada: sem isso, os pedidos que ainda estão no ar
      // trariam outros tokens e disparariam trocas concorrentes.
      concluido.current = true;
      setEstado({ fase: 'trocando', erro: null });

      let resultado: ResultadoTroca;
      try {
        resultado = await trocarRef.current(token);
      } catch {
        resultado = 'desistir';
      }
      if (!vivo) return;

      if (resultado === 'ok') {
        setEstado({ fase: 'pronto', erro: null });
        return;
      }
      if (typeof resultado === 'object') {
        setEstado({ fase: 'erro', erro: { tipo: 'recusado', mensagem: resultado.recusado } });
        return;
      }
      if (resultado === 'renovar' && tentativas.current < MAX_TENTATIVAS) {
        tentativas.current += 1;
        concluido.current = false;
        setEstado({ fase: 'pedindo', erro: null });
        pedir();
        return;
      }
      setEstado({
        fase: 'erro',
        erro: {
          tipo: 'indisponivel',
          mensagem: 'A verificação de identidade está indisponível no momento.',
        },
      });
    }

    function pedir() {
      if (concluido.current || !vivo) return;
      const pedido = { type: 'waid:identity-request' };

      // Um pedido por origem aceita: `postMessage` com destino específico é
      // descartado em silêncio quando o pai não é aquela origem, então mandar
      // para a lista inteira é o que faz o mesmo código servir aos dois
      // contextos. Continuamos SEM usar `'*'`: com destino aberto, qualquer
      // pai — inclusive um que não seja a Waid — leria o pedido.
      if (temIframe()) {
        for (const origem of origens) {
          try {
            window.parent.postMessage(pedido, origem);
          } catch {
            /* origem inválida na lista: as outras seguem valendo */
          }
        }
      }

      // No app nativo não há pai: a ponte escuta a própria janela. Postar para
      // nós mesmos parece estranho, mas é o canal que a ponte instrumenta —
      // e o `event.origin` da resposta continua sendo conferido acima.
      if (temPonteNativa()) {
        try {
          window.postMessage(pedido, window.location.origin);
        } catch {
          /* sem canal utilizável: o timeout cuida */
        }
      }
    }

    // 1. ouvinte primeiro; 2. só então o pedido.
    window.addEventListener('message', aoReceber);
    pedir();
    const reenvio = setInterval(pedir, INTERVALO_PEDIDO_MS);

    // Sem este teto a tela gira para sempre quando "Enviar identidade por token"
    // não está ligado no admin da Waid — o erro de configuração mais provável,
    // e o mais confuso de diagnosticar sem uma mensagem.
    const desistencia = setTimeout(() => {
      if (concluido.current || !vivo) return;
      setEstado({
        fase: 'erro',
        erro: {
          tipo: 'timeout',
          mensagem: 'Não conseguimos confirmar sua identidade com a plataforma.',
        },
      });
    }, TIMEOUT_MS);

    return () => {
      vivo = false;
      clearInterval(reenvio);
      clearTimeout(desistencia);
      window.removeEventListener('message', aoReceber);
    };
  }, [origens]);

  return estado;
}


/**
 * Identidade + SESSÃO. É o que os três apps do produto usam.
 *
 * Troca o token da Waid por um JWT nosso em `/auth/embed/token`, criando o
 * usuário se ele ainda não existir.
 */
export function useIdentidadeWaid({ apiBase, waidOrigin, aoAutenticar }: Opcoes): Estado {
  const aoAutenticarRef = useRef(aoAutenticar);
  aoAutenticarRef.current = aoAutenticar;

  const trocar = useCallback(
    async (token: string): Promise<ResultadoTroca> => {
      const resp = await comEsperaNoLimite(() =>
        fetch(`${apiBase}/api/v1/auth/embed/token`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ token }),
        }),
      );

      if (resp.ok) {
        aoAutenticarRef.current(await resp.json());
        return 'ok';
      }
      if (resp.status === 401) {
        const corpo = await resp.json().catch(() => null);
        // Token queimado é ocorrência normal (recarregar a página basta).
        // Pedir outro resolve; mostrar erro seria assustar à toa.
        if (tokenPrecisaSerRenovado(corpo)) return 'renovar';
      }
      if (resp.status === 403) {
        const mensagem = recusaComMensagem(await resp.json().catch(() => null));
        if (mensagem) return { recusado: mensagem };
      }
      return 'desistir';
    },
    [apiBase],
  );

  return useHandshakeWaid(waidOrigin, trocar);
}


/**
 * SÓ identidade — nome e e-mail. É o que as landing pages usam.
 *
 * Não cria sessão nem usuário: quem abre uma LP pode não ser cliente, e criar
 * cadastro a partir de um formulário de captação seria inventar consentimento.
 * Serve para pré-preencher o formulário, que antes vinha do `?email=` na URL.
 *
 * Falhar aqui não é grave: o lead digita o próprio e-mail, como em qualquer
 * outro formulário. Por isso quem chama deve tratar `erro` como "peça os dados"
 * e não como tela de erro.
 */
export function useIdentidadeSimplesWaid(
  { apiBase, waidOrigin, aoIdentificar }: OpcoesIdentidade,
): Estado {
  const aoIdentificarRef = useRef(aoIdentificar);
  aoIdentificarRef.current = aoIdentificar;

  const trocar = useCallback(
    async (token: string): Promise<'ok' | 'renovar' | 'desistir'> => {
      const resp = await comEsperaNoLimite(() =>
        fetch(`${apiBase}/api/v1/auth/embed/identidade`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
        }),
      );

      if (resp.ok) {
        const dados = await resp.json();
        aoIdentificarRef.current({ nome: dados.nome ?? null, email: dados.email });
        return 'ok';
      }
      if (resp.status === 401) {
        const corpo = await resp.json().catch(() => null);
        if (tokenPrecisaSerRenovado(corpo)) return 'renovar';
      }
      return 'desistir';
    },
    [apiBase],
  );

  return useHandshakeWaid(waidOrigin, trocar);
}
