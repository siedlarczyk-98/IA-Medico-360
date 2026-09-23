import { memo, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import { ModeChip } from './ModeChip';
import type { CitacaoBruta, Message, PubmedValidation } from '../api/orquestrador';
import { normalizarCitacoes } from '../lib/citacoes';
import { comMarcadoresDeCitacao } from '../lib/marcadoresCitacao';

const DISCLAIMER = '⚕️ Suporte à decisão clínica. A conduta é de responsabilidade exclusiva do médico assistente.';

// Defined outside component to keep reference stable across renders
/**
 * Estilos do corpo da resposta.
 *
 * Tudo aqui usa os tokens de `shared/design/tokens.css`: no telefone os valores
 * sobem um degrau sozinhos, sem `isMobile`. Antes desta passada o corpo da
 * resposta era 12–15px fixo — o texto que o médico mais lê era o menor da tela.
 *
 * As tabelas continuam com rolagem horizontal própria (`overflowX`), e não
 * quebrando as células: tabela clínica com coluna espremida troca um problema
 * de leitura por um pior, que é ler o valor na linha errada.
 */
const mdComponents: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  table: ({ children }) => (
    <div className="rolagem" style={{ overflowX: 'auto', margin: 'var(--gap-2) 0', maxWidth: '100%' }}>
      {/* `wordBreak: normal` desfaz o `break-word` herdado do corpo da
          resposta. Com ele, o navegador espremia as colunas para caber na tela
          quebrando palavras ao meio — "Apixaba/na", "Dabigatr/ana" numa tabela
          de dose. Sem ele a tabela fica mais larga que a tela e rola dentro do
          próprio contêiner, que é o comportamento pretendido. */}
      <table style={{ borderCollapse: 'collapse', minWidth: '100%', fontSize: 'var(--texto-apoio)', wordBreak: 'normal', overflowWrap: 'normal' }}>{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead style={{ background: 'var(--fill2)' }}>{children}</thead>,
  th: ({ children }) => (
    <th style={{ border: '1px solid var(--line2)', padding: 'var(--gap-2) var(--gap-3)', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>{children}</th>
  ),
  td: ({ children }) => (
    <td style={{ border: '1px solid var(--line2)', padding: 'var(--gap-2) var(--gap-3)', verticalAlign: 'top' }}>{comMarcadoresDeCitacao(children)}</td>
  ),
  tr: ({ children }) => <tr style={{ borderBottom: '1px solid var(--line2)' }}>{children}</tr>,
  p: ({ children }) => <p style={{ margin: '0 0 var(--gap-2)' }}>{comMarcadoresDeCitacao(children)}</p>,
  strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
  em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
  ul: ({ children }) => <ul style={{ margin: 'var(--gap-1) 0 var(--gap-2)', paddingLeft: 'var(--gap-5)' }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ margin: 'var(--gap-1) 0 var(--gap-2)', paddingLeft: 'var(--gap-5)' }}>{children}</ol>,
  li: ({ children }) => <li style={{ marginBottom: 'var(--gap-1)' }}>{comMarcadoresDeCitacao(children)}</li>,
  h1: ({ children }) => <h1 style={{ fontSize: 'var(--texto-titulo)', fontWeight: 700, margin: 'var(--gap-3) 0 var(--gap-2)' }}>{children}</h1>,
  h2: ({ children }) => <h2 style={{ fontSize: 'var(--texto-corpo)', fontWeight: 700, margin: 'var(--gap-3) 0 var(--gap-1)' }}>{children}</h2>,
  h3: ({ children }) => <h3 style={{ fontSize: 'var(--texto-corpo)', fontWeight: 600, margin: 'var(--gap-2) 0 var(--gap-1)' }}>{children}</h3>,
  // Bloco de código quebra linha (`pre-wrap`) em vez de rolar: no telefone uma
  // barra de rolagem por bloco é pior que a linha quebrada. `quebra-segura`
  // cobre o resto — DOI, URL de fonte e nome de medicamento não têm onde
  // quebrar e empurravam a coluna inteira para fora da tela.
  code: ({ children, className }) =>
    className
      ? <code className="quebra-segura" style={{ display: 'block', background: 'var(--fill2)', border: '1px solid var(--line2)', borderRadius: 'var(--raio-1)', padding: 'var(--gap-2) var(--gap-3)', fontSize: 'var(--texto-micro)', fontFamily: 'monospace', whiteSpace: 'pre-wrap', margin: 'var(--gap-1) 0' }}>{children}</code>
      : <code className="quebra-segura" style={{ background: 'var(--fill2)', border: '1px solid var(--line2)', borderRadius: 'var(--raio-1)', padding: '1px 5px', fontSize: 'var(--texto-micro)', fontFamily: 'monospace' }}>{children}</code>,
  pre: ({ children }) => <>{children}</>,
  blockquote: ({ children }) => <blockquote style={{ borderLeft: '3px solid var(--line2)', paddingLeft: 'var(--gap-3)', margin: 'var(--gap-1) 0', color: 'var(--pen2)' }}>{children}</blockquote>,
};

const rehypePlugins: React.ComponentProps<typeof ReactMarkdown>['rehypePlugins'] = [rehypeSanitize];
const remarkPlugins: React.ComponentProps<typeof ReactMarkdown>['remarkPlugins'] = [remarkGfm];

const STREAMING_LABELS: Record<string, string> = {
  QUICK_SEARCH:       'Buscando em fontes médicas…',
  CLINICAL_REASONING: 'Analisando o caso clínico…',
  PHARMA_CHECK:       'Checando interações…',
  PHARMA_BULA:        'Consultando bula…',
  PHARMA_RECEITA:     'Verificando receituário…',
  PHARMA_GENERICO:    'Buscando genéricos…',
  PRODUCTIVITY:       'Preparando resposta…',
  EXAM_REVIEW:        'Analisando os exames…',
  // Mais explícito que os outros de propósito: este modo NÃO streama (a API
  // rejeita streaming com ferramenta integrada), então a tela fica parada por
  // dezenas de segundos enquanto o modelo consulta as bases. Sem dizer o que
  // está acontecendo, parece travado.
  DATA_OCEAN:         'Consultando bases de dados oficiais…',
};

interface Props {
  messages: Message[];
  streaming?: boolean;
  streamingMode?: string;
  /** Texto pronto, metadados a caminho. Não bloqueia a digitação. */
  finalizing?: boolean;
  /** Muda a cada pergunta ENVIADA: ancora a pergunta no topo da área visível. */
  scrollToBottomTrigger?: number;
  /** Muda a cada conversa ABERTA: vai direto ao fim, sem herdar a rolagem anterior. */
  conversationOpenedTrigger?: number;
  /** Conversa escolhida na lateral, ainda chegando da rede. */
  loading?: boolean;
  /** Repete o último envio. Aparece só na mensagem marcada `podeTentarDeNovo`. */
  onRetry?: () => void;
}

export function ChatView({ messages, streaming, streamingMode, finalizing, scrollToBottomTrigger, conversationOpenedTrigger, loading, onRetry }: Props) {
  const areaRef = useRef<HTMLDivElement>(null);
  const turnoRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // O turno que está ancorado agora, para desfazer a âncora quando ela muda de dono.
  const ancoradoRef = useRef<HTMLDivElement | null>(null);

  const soltarAncora = () => {
    if (ancoradoRef.current) ancoradoRef.current.style.minHeight = '';
    ancoradoRef.current = null;
  };

  // AO ENVIAR: a pergunta sobe para o topo e o turno ganha a altura da área
  // visível, de modo que a resposta preenche a tela de cima para baixo sem o
  // médico encostar na rolagem. Antes rolava-se até o fim UMA vez, no envio: a
  // resposta crescia para fora da tela e era preciso rolar à mão por até um
  // minuto, a cada pergunta.
  //
  // A altura vai DIRETO no estilo do elemento, sem estado: é um valor medido no
  // DOM e aplicado no DOM, e passar por `setState` custaria um render a mais só
  // para transportar um número (além de ser `setState` síncrono em efeito).
  useEffect(() => {
    if (scrollToBottomTrigger === undefined || scrollToBottomTrigger === 0) return;
    const turno = turnoRef.current;
    if (!turno) return;
    soltarAncora(); // o turno anterior não pode ficar com um vão da altura da tela
    turno.style.minHeight = `${areaRef.current?.clientHeight ?? 0}px`;
    ancoradoRef.current = turno;
    turno.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [scrollToBottomTrigger]);

  // AO ABRIR uma conversa: fim da conversa, na hora. Sem isto a rolagem da
  // conversa anterior ficava, e a recém-aberta aparecia num ponto qualquer. E a
  // âncora sai, senão sobraria um vão em branco do tamanho da tela no fim.
  useEffect(() => {
    if (conversationOpenedTrigger === undefined || conversationOpenedTrigger === 0) return;
    soltarAncora();
    bottomRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' });
  }, [conversationOpenedTrigger]);

  // Um contêiner POR TURNO (pergunta + resposta), com chave estável. No React a
  // chave vale por pai: com um contêiner só para "o último turno", cada pergunta
  // nova fazia a resposta anterior mudar de pai e ser REMONTADA — Markdown
  // reinterpretado e estado perdido (referências expandidas). Assim o turno
  // antigo nunca muda de lugar; só a âncora passa para o turno novo.
  const turnos: { inicio: number; mensagens: Message[] }[] = [];
  messages.forEach((msg, i) => {
    if (msg.role === 'user' || turnos.length === 0) turnos.push({ inicio: i, mensagens: [] });
    turnos[turnos.length - 1].mensagens.push(msg);
  });
  if (turnos.length === 0) turnos.push({ inicio: 0, mensagens: [] });

  return (
    <div ref={areaRef} className="rolagem" style={{ flex: 1, padding: 'var(--gap-5) var(--margem-tela) 0', display: 'flex', justifyContent: 'center' }}>
      {/* `--coluna-leitura` é `min(720px, 100%)`: mesma largura no desktop, e no
          telefone acompanha a tela em vez de forçar rolagem horizontal. */}
      <div style={{ width: 'var(--coluna-leitura)', paddingBottom: 'var(--gap-4)' }}>
        {turnos.map((turno, n) => {
          const ultimo = n === turnos.length - 1;
          return (
            <div
              key={turno.inicio}
              ref={ultimo ? turnoRef : undefined}
              data-testid={ultimo ? 'ultimo-turno' : undefined}
            >
              {turno.mensagens.map((msg, i) => (
                msg.role === 'user'
                  ? <UserMessage key={turno.inicio + i} content={msg.content} attachments={msg.attachments} />
                  : <AssistantMessage key={turno.inicio + i} content={msg.content} mode={msg.mode} confidence={msg.confidence} citations={msg.citations} pubmed_validation={msg.pubmed_validation} isFallback={msg.is_fallback} />
              ))}
              {ultimo && onRetry && !streaming && turno.mensagens.at(-1)?.podeTentarDeNovo && (
                <button
                  onClick={onRetry}
                  style={{
                    margin: '0 0 16px', padding: '0 var(--gap-4)', borderRadius: 8,
                    minHeight: 'var(--toque-min)',
                    border: '1px solid var(--line)', background: '#fff', color: 'var(--petrol)',
                    fontSize: 'var(--texto-apoio)', fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  Tentar novamente
                </button>
              )}
              {ultimo && streaming && <ThinkingIndicator mode={streamingMode} />}
              {ultimo && !streaming && finalizing && <ReferencesPending />}
            </div>
          );
        })}
        {loading && (
          <p role="status" style={{ fontSize: 'var(--texto-apoio)', color: 'var(--pen2)', margin: '8px 0' }}>
            Carregando conversa…
          </p>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

const ATTACHMENT_ICON: Record<string, string> = {
  pdf: '📄',
  docx: '📝',
  xlsx: '📊',
  image: '🖼',
};

const UserMessage = memo(function UserMessage({ content, attachments }: {
  content: string;
  attachments?: Array<{ id?: string; file_name: string; file_type: string }>;
}) {
  return (
    <div data-testid="user-message" style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 18 }}>
      <div style={{ maxWidth: 'var(--balao-usuario)', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--gap-1)' }}>
        {attachments && attachments.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, justifyContent: 'flex-end' }}>
            {attachments.map((att, idx) => (
              <div
                key={att.id ?? `${att.file_name}-${idx}`}
                data-testid="mensagem-anexo"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '3px 9px', borderRadius: 8,
                  background: 'var(--fill2)', border: '1px solid var(--line2)',
                  fontSize: 'var(--texto-micro)', color: 'var(--pen2)',
                }}
              >
                {ATTACHMENT_ICON[att.file_type] ?? '📎'}
                <span style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {att.file_name}
                </span>
              </div>
            ))}
          </div>
        )}
        {content && (
          <div className="quebra-segura" style={{
            background: 'var(--ink)', color: '#fff',
            padding: 'var(--gap-3) var(--gap-4)', borderRadius: 'var(--raio-3)', borderBottomRightRadius: 'var(--raio-1)',
            fontSize: 'var(--texto-corpo)', lineHeight: 'var(--linha-corpo)',
          }}>{content}</div>
        )}
      </div>
    </div>
  );
});

/**
 * Marca uma resposta que NÃO veio do modelo do modo.
 *
 * Vem ANTES do texto, não depois: o aviso existe para mudar como o médico LÊ o
 * que está abaixo, e um rodapé chegaria tarde demais.
 *
 * Por que isto importa no Data Ocean: aquele modo não tem fallback por decisão
 * — cair para outro modelo devolveria números plausíveis inventados no lugar de
 * uma consulta ao DATASUS, e o desenho escolheu "falhar visivelmente". Só que a
 * mensagem genérica de erro era gravada e reexibida com a mesma aparência de
 * uma resposta legítima, e o médico que reabria a conversa lia "não salvou"
 * onde o correto era "a consulta falhou".
 */
function AvisoFallback() {
  return (
    <div
      role="note"
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 6,
        margin: '0 0 8px', padding: '6px 10px',
        fontSize: 'var(--texto-micro)', lineHeight: 1.45,
        color: 'var(--pen2)', background: 'var(--fill2)',
        border: '1px solid var(--line2)', borderRadius: 6,
      }}
    >
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }}>
        <path d="M8 5.5v3.2M8 11h.01M8 1.8 1.5 13.2h13L8 1.8z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>
        A consulta não foi concluída — esta resposta <strong>não vem das bases consultadas
        pelo modo escolhido</strong>. Vale refazer a pergunta.
      </span>
    </div>
  );
}

const AssistantMessage = memo(function AssistantMessage({ content, mode, confidence, citations, pubmed_validation, isFallback }: { content: string; mode?: string; confidence?: number; citations?: CitacaoBruta[]; pubmed_validation?: PubmedValidation; isFallback?: boolean }) {
  // Conversa antiga traz `string[]`; nova, objetos com titulo. Ver `citacoes.ts`.
  const fontes = useMemo(() => normalizarCitacoes(citations ?? []), [citations]);

  const rendered = useMemo(() => (
    <ReactMarkdown rehypePlugins={rehypePlugins} remarkPlugins={remarkPlugins} components={mdComponents}>
      {content}
    </ReactMarkdown>
  ), [content]);

  return (
    <div data-testid="assistant-message" style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 24 }}>
      <AssistantAvatar />
      <div style={{ flex: 1, minWidth: 0, paddingTop: 4 }}>
        {mode && (
          <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            {['raciocinio','farmaco','busca','produtividade','exames'].includes(mode)
              ? <ModeChip mode={mode} confidence={confidence} />
              : <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '4px 10px', fontSize: 'var(--texto-micro)', fontWeight: 600,
                  color: 'var(--petrol)', background: 'var(--fill2)',
                  border: '1px solid var(--line2)', borderRadius: 999,
                }}>{mode}</span>
            }
          </div>
        )}
        {isFallback && <AvisoFallback />}
        {/* O texto que o médico mais lê. Estava fixo em 13px — a varredura
            por fontes ≤ 12,5 passou por ele. */}
        <div style={{ fontSize: 'var(--texto-corpo)', color: 'var(--ink)', lineHeight: 'var(--linha-corpo)', wordBreak: 'break-word' }}>
          {rendered}
        </div>
        {fontes.length > 0 && (
          <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--line2)' }}>
            <div style={{ fontSize: 'var(--texto-micro)', fontWeight: 700, color: 'var(--pen3)', letterSpacing: 0.5, textTransform: 'uppercase', marginBottom: 4 }}>Fontes</div>
            {/* Sem `gap`: o espaço entre as fontes agora vem da altura mínima
                de cada link, que é o alvo de toque. Com os dois, a lista
                dobraria de tamanho. */}
            <ol style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column' }}>
              {fontes.map((fonte, i) => (
                <li key={i} className="quebra-segura" style={{ fontSize: 'var(--texto-apoio)', color: 'var(--pen2)' }}>
                  <a href={fonte.url} target="_blank" rel="noopener noreferrer"
                    title={fonte.url}
                    style={{
                      color: 'var(--petrol)', textDecoration: 'none',
                      // Alvo de toque: o link tinha a altura da linha (~19px).
                      display: 'inline-flex', alignItems: 'center', minHeight: 'var(--toque-min)',
                      // Título de artigo quebra em palavras; domínio, que não
                      // tem espaço, precisa de `break-all` para não estourar a
                      // largura da coluna no celular.
                      wordBreak: fonte.temTitulo ? 'break-word' : 'break-all',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.textDecoration = 'underline')}
                    onMouseLeave={e => (e.currentTarget.style.textDecoration = 'none')}
                  >{fonte.rotulo}</a>
                </li>
              ))}
            </ol>
          </div>
        )}
        {pubmed_validation && <PubmedSection validation={pubmed_validation} />}
        <div style={{
          marginTop: 14, fontSize: 'var(--texto-micro)', color: 'var(--pen3)',
          borderTop: '1px solid var(--line2)', paddingTop: 10,
        }}>
          {DISCLAIMER}
        </div>
      </div>
    </div>
  );
});

function PubmedSection({ validation }: { validation: PubmedValidation }) {
  const [showGuidelines, setShowGuidelines] = useState(false);
  const { cited_verified, newer_guidelines } = validation;

  return (
    <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--line2)' }}>
      {cited_verified.length > 0 && (
        <>
          <div style={{ fontSize: 'var(--texto-micro)', fontWeight: 700, color: 'var(--pen3)', letterSpacing: 0.5, textTransform: 'uppercase', marginBottom: 4 }}>
            Referências verificadas no PubMed
          </div>
          <ol style={{ margin: '0 0 6px', paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 3 }}>
            {cited_verified.map((c, i) => (
              <li key={i} className="quebra-segura" style={{ fontSize: 'var(--texto-apoio)', color: 'var(--pen2)' }}>
                {c.pmid
                  ? <a
                      href={`https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'var(--petrol)', textDecoration: 'none' }}
                      onMouseEnter={e => (e.currentTarget.style.textDecoration = 'underline')}
                      onMouseLeave={e => (e.currentTarget.style.textDecoration = 'none')}
                    >{c.title}</a>
                  : <span>{c.title}</span>
                }
              </li>
            ))}
          </ol>
        </>
      )}
      {newer_guidelines.length > 0 && (
        <div>
          <button
            onClick={() => setShowGuidelines(v => !v)}
            style={{
              // `padding: 0` deixava como alvo só o texto de 11px. A altura
              // mínima aumenta a área tocável sem mudar o desenho.
              background: 'none', border: 'none', padding: 0, cursor: 'pointer',
              minHeight: 'var(--toque-min)',
              fontSize: 'var(--texto-micro)', color: 'var(--petrol)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
            }}
          >
            <span style={{ fontSize: 'var(--texto-micro)' }}>{showGuidelines ? '▾' : '▸'}</span>
            Diretrizes recentes relacionadas ({newer_guidelines.length})
          </button>
          {showGuidelines && (
            <ul style={{ margin: '4px 0 0', paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 3 }}>
              {newer_guidelines.map((a, i) => (
                <li key={i} className="quebra-segura" style={{ fontSize: 'var(--texto-apoio)', color: 'var(--pen2)' }}>
                  <a
                    href={`https://pubmed.ncbi.nlm.nih.gov/${a.pmid}/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--petrol)', textDecoration: 'none' }}
                    onMouseEnter={e => (e.currentTarget.style.textDecoration = 'underline')}
                    onMouseLeave={e => (e.currentTarget.style.textDecoration = 'none')}
                  >{a.article_title}</a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// Modos cuja espera é longa o bastante para exigir mais que três pontinhos.
//
// Medição em produção (2026-09-08): uma consulta ao Data Ocean levou 97,9s. O
// fluxo agêntico roda inteiro do lado da Maritaca — decide quais bases
// consultar, executa, cruza — e a API não aceita streaming com a ferramenta
// ligada. Ou seja: não há como mostrar texto parcial, e a demora não é do
// nosso código.
//
// O que dá para mudar é a EXPECTATIVA. Uma frase estática por 98 segundos é
// indistinguível de uma tela travada; um cronômetro correndo e etapas que
// avançam dizem "está trabalhando" sem prometer o que não se pode cumprir.
const MODOS_DE_ESPERA_LONGA: Record<string, { etapas: string[]; avisoSegundos: number }> = {
  DATA_OCEAN: {
    // As etapas são ILUSTRATIVAS, não o progresso real: o fluxo agêntico é
    // interno à Maritaca e não expõe em que passo está. Elas descrevem o que
    // a ferramenta de fato faz, na ordem em que faz — o médico entende o que
    // está acontecendo, e nenhuma delas afirma um estado que não sabemos.
    etapas: [
      'Escolhendo as bases de dados…',
      'Consultando fontes oficiais…',
      'Cruzando os dados encontrados…',
      'Montando a resposta com as fontes…',
    ],
    // A partir daqui, dizer explicitamente que é normal demorar.
    avisoSegundos: 25,
  },
};

function ThinkingIndicator({ mode }: { mode?: string }) {
  const longo = mode ? MODOS_DE_ESPERA_LONGA[mode] : undefined;
  const [segundos, setSegundos] = useState(0);

  useEffect(() => {
    if (!longo) return;
    const id = setInterval(() => setSegundos(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [longo]);

  // Uma etapa a cada 8s, parando na última: o contador continua correndo, mas
  // as etapas não voltam ao início nem inventam progresso que não existe.
  const etapa = longo
    ? longo.etapas[Math.min(Math.floor(segundos / 8), longo.etapas.length - 1)]
    : undefined;
  const label = etapa ?? (mode && STREAMING_LABELS[mode]) ?? 'Processando…';

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <AssistantAvatar />
      <div style={{ paddingTop: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {[0, 1, 2].map(i => (
            <div key={i} style={{
              width: 5, height: 5, borderRadius: '50%', background: 'var(--green)',
              animation: 'pulse 1.2s ease-in-out infinite',
              animationDelay: `${i * 0.2}s`,
            }} />
          ))}
          <span style={{ fontSize: 'var(--texto-apoio)', color: 'var(--pen2)', fontWeight: 500 }}>
            {label}
          </span>
          {longo && segundos > 0 && (
            // O cronômetro é o que mais separa "trabalhando" de "travado":
            // um número que muda prova que a página está viva.
            <span style={{ fontSize: 'var(--texto-micro)', color: 'var(--pen3)', fontVariantNumeric: 'tabular-nums' }}>
              {segundos}s
            </span>
          )}
        </div>
        {longo && segundos >= longo.avisoSegundos && (
          <p style={{ fontSize: 'var(--texto-micro)', color: 'var(--pen3)', margin: '6px 0 0', lineHeight: 1.45, maxWidth: 420 }}>
            Consultas a bases oficiais levam mais tempo que uma busca comum —
            normalmente entre 1 e 2 minutos. A resposta vem com os números e a
            fonte de cada um.
          </p>
        )}
      </div>
    </div>
  );
}


// Nota de rodapé, não indicador de carregamento: a resposta já está completa
// acima e o médico pode seguir. Isto só avisa que as referências ainda chegam.
function ReferencesPending() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '2px 0 8px 42px', fontSize: 'var(--texto-apoio)', color: 'var(--pen2)',
    }}>
      <div style={{
        width: 5, height: 5, borderRadius: '50%', background: 'var(--pen2)',
        animation: 'pulse 1.2s ease-in-out infinite',
      }} />
      <span>Verificando referências…</span>
    </div>
  );
}

function AssistantAvatar() {
  return (
    // A classe existe para a casca mobile esconder o avatar: no telefone ele
    // e o recuo que cria custam ~45 px de uma coluna de 360 (ver `mobile.css`).
    <div className="cv-avatar" style={{
      width: 30, height: 30, borderRadius: 8, background: 'var(--mint)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    }}>
      <svg width="14" height="14" viewBox="0 0 32 32" fill="none">
        <path d="M3 26 L3 10 Q3 5 8 5 Q12 5 13 9 L16 22 L19 9 Q20 5 24 5 Q29 5 29 10 L29 26"
              stroke="#014751" strokeWidth="3.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="8" cy="13" r="1.6" fill="#00d17d" />
      </svg>
    </div>
  );
}
