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

export type FaseIdentidade = 'pedindo' | 'trocando' | 'pronto' | 'erro';

export interface MotivoErro {
  /** `timeout` | `indisponivel` | `desconhecido` */
  tipo: 'timeout' | 'indisponivel' | 'desconhecido';
  mensagem: string;
}

export interface RespostaSessao {
  access_token: string;
  onboarding_complete: boolean;
}

interface Opcoes {
  apiBase: string;
  /** Origem da área de membros da Waid: destino do pedido e origem esperada. */
  waidOrigin: string;
  /** Chamado com a resposta do backend quando a sessão é criada. */
  aoAutenticar: (resposta: RespostaSessao) => void;
}

interface Estado {
  fase: FaseIdentidade;
  erro: MotivoErro | null;
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
export function useIdentidadeWaid({ apiBase, waidOrigin, aoAutenticar }: Opcoes): Estado {
  const [estado, setEstado] = useState<Estado>({ fase: 'pedindo', erro: null });

  // Refs, e não estado: mudanças aqui não devem re-renderizar nem recriar o
  // efeito — recriá-lo removeria o ouvinte no meio do handshake.
  const concluido = useRef(false);
  const tentativas = useRef(0);
  const aoAutenticarRef = useRef(aoAutenticar);
  aoAutenticarRef.current = aoAutenticar;

  const trocar = useCallback(
    async (token: string): Promise<'ok' | 'renovar' | 'desistir'> => {
      const resp = await fetch(`${apiBase}/api/v1/auth/embed/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ token }),
      });

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
      return 'desistir';
    },
    [apiBase],
  );

  useEffect(() => {
    let vivo = true;

    async function aoReceber(event: MessageEvent) {
      if (event.origin !== waidOrigin) return;
      if ((event.data as { type?: string })?.type !== 'waid:identity') return;
      if (concluido.current || !vivo) return;

      const token = (event.data as { token?: string }).token;
      if (!token) return;

      // Marca antes da chamada: sem isso, os pedidos que ainda estão no ar
      // trariam outros tokens e disparariam trocas concorrentes.
      concluido.current = true;
      setEstado({ fase: 'trocando', erro: null });

      let resultado: 'ok' | 'renovar' | 'desistir';
      try {
        resultado = await trocar(token);
      } catch {
        resultado = 'desistir';
      }
      if (!vivo) return;

      if (resultado === 'ok') {
        setEstado({ fase: 'pronto', erro: null });
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
      window.parent.postMessage({ type: 'waid:identity-request' }, waidOrigin);
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
  }, [waidOrigin, trocar]);

  return estado;
}
