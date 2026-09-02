/**
 * Diagnóstico do embed — para quando não há devtools.
 *
 * POR QUE EXISTE
 * O handshake de identidade funciona no navegador e não funciona dentro dos
 * aplicativos da Waid. Sem console num app nativo, não dá para saber se a
 * página sequer está dentro de um iframe, se recebe mensagem alguma, ou se a
 * origem é diferente da esperada — e cada uma dessas causas tem um dono
 * diferente.
 *
 * Esta tela responde isso na própria tela do celular. O uso é: configurar uma
 * seção temporária na Waid apontando para `/diagnostico-embed`, abrir no app,
 * e mandar o print (ou o texto copiado) para quem cuida da plataforma.
 *
 * NÃO É TELA DE PRODUTO. Não tem link para ela em lugar nenhum — só é
 * alcançada por quem digita a rota. Não mostra dado de paciente nem token de
 * sessão; o token da Waid aparece truncado, porque é de uso único e de 5
 * minutos, e vê-lo chegar é justamente o que se quer provar.
 */

import { useEffect, useRef, useState } from 'react';

const WAID_ORIGIN =
  import.meta.env.VITE_WAID_ORIGIN ?? 'https://adminportalmedico360.curseduca.pro';

interface MensagemVista {
  em: string;
  origin: string;
  tipo: string;
  temToken: boolean;
}

export function DiagnosticoEmbedPage() {
  const [mensagens, setMensagens] = useState<MensagemVista[]>([]);
  const [pedidos, setPedidos] = useState(0);
  const [copiado, setCopiado] = useState(false);
  const inicio = useRef(Date.now());

  /**
   * `localStorage` funciona AQUI, neste contexto?
   *
   * Somos um iframe cross-origin. Navegadores e webviews bloqueiam ou
   * particionam armazenamento de terceiros nessa situação — e o modo de falha é
   * traiçoeiro: em alguns, escrever lança; em outros, escreve e some depois;
   * em outros ainda, o valor fica isolado por sessão. Por isso o teste é de
   * ida e volta (escreve, lê, compara), não só um `try` em volta do `setItem`.
   *
   * Se isto falhar, TUDO se explica: o handshake funciona, a troca funciona, o
   * token é guardado, o `RequireAuth` não o encontra no próximo render e manda
   * para o login. Vale para o token novo e valia para o fluxo por e-mail — que
   * é justamente o que nunca funcionou nos apps.
   */
  function testarArmazenamento(): string {
    const chave = '__m360_teste_armazenamento';
    try {
      const valor = String(Date.now());
      localStorage.setItem(chave, valor);
      const lido = localStorage.getItem(chave);
      localStorage.removeItem(chave);
      if (lido !== valor) return 'FALHA — escreveu mas leu diferente';
      return 'OK';
    } catch (e) {
      return `BLOQUEADO — ${e instanceof Error ? e.name : 'erro'}`;
    }
  }

  // Colhido uma vez: o que descreve o CONTEXTO em que a página abriu.
  const contexto = useRef({
    url: window.location.href,
    dentroDeIframe: window.parent !== window,
    referrer: document.referrer || '(vazio)',
    origemEsperada: WAID_ORIGIN,
    armazenamento: testarArmazenamento(),
    cookiesHabilitados: navigator.cookieEnabled ? 'SIM' : 'NAO',
    userAgent: navigator.userAgent,
  });

  useEffect(() => {
    function aoReceber(event: MessageEvent) {
      // Registra TUDO, sem filtrar por origem — o ponto é justamente descobrir
      // qual origem chega. Filtrar aqui esconderia a resposta que procuramos.
      const dados = event.data as { type?: string; token?: string } | null;
      setMensagens(atual => [
        ...atual.slice(-9),
        {
          em: `${((Date.now() - inicio.current) / 1000).toFixed(1)}s`,
          origin: event.origin || '(vazia)',
          tipo: typeof dados?.type === 'string' ? dados.type : typeof event.data,
          temToken: Boolean(dados?.token),
        },
      ]);
    }

    window.addEventListener('message', aoReceber);

    function pedir() {
      // Para `*`, de propósito: aqui queremos saber se ALGUÉM responde, e um
      // destino específico errado faria o browser descartar em silêncio — que
      // é exatamente a dúvida a eliminar.
      try {
        window.parent.postMessage({ type: 'waid:identity-request' }, '*');
        setPedidos(n => n + 1);
      } catch {
        /* sem pai acessível — já está registrado em `dentroDeIframe` */
      }
    }

    pedir();
    const t = setInterval(pedir, 2000);
    return () => {
      clearInterval(t);
      window.removeEventListener('message', aoReceber);
    };
  }, []);

  const relatorio = [
    `URL              : ${contexto.current.url}`,
    `Dentro de iframe : ${contexto.current.dentroDeIframe ? 'SIM' : 'NAO'}`,
    `document.referrer: ${contexto.current.referrer}`,
    `Origem esperada  : ${contexto.current.origemEsperada}`,
    `localStorage     : ${contexto.current.armazenamento}`,
    `Cookies          : ${contexto.current.cookiesHabilitados}`,
    `Pedidos enviados : ${pedidos}`,
    `Mensagens vistas : ${mensagens.length}`,
    ...mensagens.map(m => `  [${m.em}] origem=${m.origin} tipo=${m.tipo} token=${m.temToken ? 'sim' : 'nao'}`),
    `UserAgent        : ${contexto.current.userAgent}`,
  ].join('\n');

  const veredito = !contexto.current.dentroDeIframe
    ? 'A página NÃO está dentro de um iframe. Sem iframe, a plataforma não tem como entregar a identidade — nem por evento, nem por parâmetro na URL.'
    : mensagens.length === 0
      ? 'Está dentro de um iframe, mas nenhuma mensagem chegou. O envio de identidade por token pode não estar ligado nesta seção.'
      : 'Mensagens recebidas — confira a origem abaixo contra a origem esperada.';

  return (
    <div style={{ padding: 20, fontFamily: 'system-ui, sans-serif', color: '#0e252d', background: '#fdfff4', minHeight: '100vh' }}>
      <h1 style={{ fontSize: 18, margin: '0 0 4px' }}>Diagnóstico do embed</h1>
      <p style={{ fontSize: 13, color: '#6b7a80', margin: '0 0 16px' }}>
        Tela técnica. Tire um print desta página inteira.
      </p>

      <div style={{
        background: '#eef2f1', border: '1px solid #d8ddde', borderRadius: 10,
        padding: 14, fontSize: 13, lineHeight: 1.5, marginBottom: 16,
      }}>
        <strong>Leitura:</strong> {veredito}
      </div>

      <pre style={{
        background: '#fff', border: '1px solid #d8ddde', borderRadius: 10,
        padding: 14, fontSize: 12, lineHeight: 1.6, overflowX: 'auto',
        whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: '0 0 16px',
      }}>{relatorio}</pre>

      <button
        onClick={() => {
          navigator.clipboard?.writeText(relatorio).then(
            () => setCopiado(true),
            () => setCopiado(false),
          );
        }}
        style={{
          padding: '10px 16px', borderRadius: 8, border: 'none',
          background: '#014751', color: '#fff', fontSize: 14, fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        {copiado ? 'Copiado' : 'Copiar relatório'}
      </button>
    </div>
  );
}
