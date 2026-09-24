/**
 * Escolha de temas — a primeira tela de quem abre o app.
 *
 * DESENHO: CONFIRMAR, NÃO PREENCHER
 * A primeira versão era uma parede de 51 chips. Ela pedia um trabalho cujo
 * resultado já temos: a especialidade veio do onboarding do app principal. Esta
 * mostra só os temas dessa especialidade, em duas colunas — o resto da taxonomia
 * fica atrás de "ver todos".
 *
 * POR QUE SÓ O NOME DO TEMA NA LINHA
 * Uma versão anterior listava até 2 títulos de exemplo por tema, e outra um
 * contador de destaques. As duas ficavam pesadas: 12 temas viravam uma parede.
 * A linha é só o tema, e os títulos de exemplo continuam vindo do backend —
 * aparecem no hover, para quem quiser conferir o que o tema traz.
 *
 * O que se perde: a tela deixa de mostrar, à primeira vista, que um tema andou
 * quieto. Foi decisão de produto — a leveza valeu mais que esse sinal.
 *
 * A FRASE DE ABERTURA TROCA SOZINHA
 * `origem_sugestao` vem do backend. Enquanto não há colegas suficientes da
 * especialidade, a tela fala em nome da curadoria — que é verdade, nós
 * selecionamos mesmo. Quando o dado existir, ela passa a falar em nome dos
 * colegas, com percentual real. Afirmar comportamento de colegas antes disso
 * seria estatística inventada, apresentada a médicos.
 */
import { useEffect, useMemo, useState } from 'react';
import { useFormularioSalvo, usePreservarFormulario } from '@shared/embed/formulario';
import { getTokenPayload } from '../lib/auth';
import {
  adicionarPalavra,
  buscarMeusTemas,
  buscarPalavras,
  buscarPreferencias,
  preverPalavra,
  removerPalavra,
  salvarMeusTemas,
  salvarPreferencias,
  type AgendaDigest,
  type Faixa,
  type Frequencia,
  type OrigemSugestao,
  type PalavraChave,
  type Tema,
  type TemaSugerido,
} from '../api/news';

const COR = {
  tinta: '#0e252d',
  petroleo: '#014751',
  verde: '#00d17d',
  menta: '#aef6c6',
  algodao: '#fdfff4',
  linha: '#d9e6e2',
  aviso: '#8a5a06',
  avisoFundo: '#fdeccb',
} as const;

const FONTE = "'Plus Jakarta Sans', -apple-system, 'Segoe UI', sans-serif";

// Índice = `dia_semana` do backend, que segue o `weekday()` do Python: 0 é
// segunda. Não reordenar sem mexer no outro lado.
const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'] as const;

// A HORA APARECE NO BOTÃO de propósito. "Manhã" sozinho deixa a pessoa
// adivinhando se são 6h ou 11h; com "7h" ela sabe exatamente o que escolheu e
// não precisa descobrir pelo primeiro e-mail. É horário de Brasília — a
// conversão mora em `news_digest_agenda.py`, no backend.
const FAIXAS: { id: Faixa; rotulo: string; hora: string }[] = [
  { id: 'manha', rotulo: 'Manhã', hora: '7h' },
  { id: 'tarde', rotulo: 'Tarde', hora: '13h' },
  { id: 'noite', rotulo: 'Noite', hora: '19h' },
];

interface Props {
  primeiraVez: boolean;
  aoConcluir: () => void;
  aoCancelar?: () => void;
}

/** Ignora acento e caixa, para "cardiaca" achar "cardíaca". */
function normalizar(texto: string): string {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

/**
 * O que volta depois de uma reentrada no meio da edição (item 68) — ver
 * `shared/embed/formulario.ts` e `sessaoExpirou` em `lib/auth.ts`.
 */
/** O padrão do backend (diário, de manhã). */
const AGENDA_PADRAO: AgendaDigest = { frequencia: 'diario', dia_semana: 0, faixa: 'manha' };

interface EdicaoGuardada {
  marcados: string[];
  email: boolean;
  agenda: AgendaDigest;
  rascunho: string;
}

export function TemasPage({ primeiraVez, aoConcluir, aoCancelar }: Props) {
  const salvo = useFormularioSalvo<Partial<EdicaoGuardada>>('temas', getTokenPayload()?.sub);
  const [sugeridos, setSugeridos] = useState<TemaSugerido[]>([]);
  const [disponiveis, setDisponiveis] = useState<Tema[]>([]);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [origem, setOrigem] = useState<OrigemSugestao>('curadoria');
  const [especialidade, setEspecialidade] = useState<string | null>(null);
  const [nome, setNome] = useState<string | null>(null);

  const [palavras, setPalavras] = useState<PalavraChave[]>([]);
  const [rascunho, setRascunho] = useState(salvo?.rascunho ?? '');
  const [previa, setPrevia] = useState<{ destaques: number } | { erro: string } | null>(null);
  const [salvandoPalavra, setSalvandoPalavra] = useState(false);

  const [verTodos, setVerTodos] = useState(false);
  const [busca, setBusca] = useState('');
  const [email, setEmail] = useState(false);
  // A agenda nasce com o padrão do backend e é substituída no carregamento.
  // Nunca fica indefinida: a tela não tem um estado "sem horário".
  const [agenda, setAgenda] = useState<AgendaDigest>(AGENDA_PADRAO);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  useEffect(() => {
    let cancelado = false;

    async function carregar() {
      try {
        const [temas, prefs, chaves] = await Promise.all([
          buscarMeusTemas(),
          buscarPreferencias(),
          buscarPalavras(),
        ]);
        if (cancelado) return;
        setSugeridos(temas.sugeridos);
        setDisponiveis(temas.disponiveis);
        setOrigem(temas.origem_sugestao);
        setEspecialidade(temas.especialidade);
        setNome(temas.primeiro_nome);
        const base = temas.ja_escolheu ? temas.selecionados : temas.sugeridos;
        // O que o médico tinha marcado antes da reentrada vence o que está salvo
        // no servidor: é justamente a edição que ele ainda não tinha salvado.
        setMarcados(new Set(salvo?.marcados ?? base.map((t) => t.id)));
        setEmail(salvo?.email ?? prefs.email);
        // `?? AGENDA_PADRAO`: backend antigo, no descompasso de um deploy, não
        // manda a agenda — ver `PreferenciasNoticias`.
        const doServidor = prefs.agenda ?? AGENDA_PADRAO;
        setAgenda(salvo?.agenda ? { ...doServidor, ...salvo.agenda } : doServidor);
        setPalavras(chaves);
      } catch (e) {
        if (!cancelado) setErro(e instanceof Error ? e.message : 'Erro ao carregar');
      } finally {
        if (!cancelado) setCarregando(false);
      }
    }

    carregar();
    return () => {
      cancelado = true;
    };
  }, [salvo]);

  // Só depois de carregar: antes disso as marcações estão vazias, e guardá-las
  // faria a volta mostrar tudo desmarcado — um toque em salvar apagaria os temas.
  usePreservarFormulario(
    'temas',
    carregando ? undefined : { marcados: [...marcados], email, agenda, rascunho },
  );

  // Preview enquanto digita. É o que impede a palavra-chave de ser um ato de
  // fé: um termo que não casa com nada aparece como zero na hora.
  useEffect(() => {
    const termo = rascunho.trim();
    let cancelado = false;

    // O `setPrevia(null)` vive dentro do timer, e nao no corpo do efeito:
    // chamar setState de forma sincrona ali dispara um render em cascata a cada
    // tecla digitada.
    const timer = setTimeout(async () => {
      if (termo.length < 2) {
        if (!cancelado) setPrevia(null);
        return;
      }
      try {
        const r = await preverPalavra(termo);
        if (!cancelado) setPrevia({ destaques: r.destaques });
      } catch (e) {
        if (!cancelado) setPrevia({ erro: e instanceof Error ? e.message : 'Termo inválido' });
      }
    }, 350);
    return () => {
      cancelado = true;
      clearTimeout(timer);
    };
  }, [rascunho]);

  const idsSugeridos = useMemo(() => new Set(sugeridos.map((t) => t.id)), [sugeridos]);
  const outros = useMemo(() => {
    const q = normalizar(busca.trim());
    return disponiveis
      .filter((t) => !idsSugeridos.has(t.id))
      .filter((t) => !q || normalizar(t.nome_pt).includes(q));
  }, [disponiveis, idsSugeridos, busca]);

  function alternar(id: string) {
    setMarcados((atual) => {
      const novo = new Set(atual);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  }

  async function acrescentarPalavra() {
    const termo = rascunho.trim();
    if (!termo) return;
    setSalvandoPalavra(true);
    try {
      setPalavras(await adicionarPalavra(termo));
      setRascunho('');
      setPrevia(null);
    } catch (e) {
      setPrevia({ erro: e instanceof Error ? e.message : 'Não foi possível adicionar' });
    } finally {
      setSalvandoPalavra(false);
    }
  }

  async function tirarPalavra(termo: string) {
    setPalavras(await removerPalavra(termo));
  }

  async function salvar() {
    setSalvando(true);
    setErro('');
    try {
      await salvarMeusTemas([...marcados]);
      await salvarPreferencias(email, agenda);
      aoConcluir();
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Erro ao salvar');
      setSalvando(false);
    }
  }

  if (carregando) return <div style={E.centro}>Carregando…</div>;

  const social = origem === 'social';

  // O nome pode nao existir — o SSO de embed cria o usuario so com e-mail. As
  // duas versoes do titulo sao escritas inteiras, e nao concatenadas com um
  // pedaco opcional: "Ruben, este e o seu ponto de partida" e ", este e o seu
  // ponto de partida" nao sao a mesma frase com e sem prefixo.
  const titulo = !primeiraVez
    ? nome
      ? `Seus temas, ${nome}`
      : 'Seus temas'
    : social
      ? nome
        ? `${nome}, veja o que seus colegas acompanham`
        : 'Veja o que seus colegas acompanham'
      : nome
        ? `${nome}, este é o seu ponto de partida`
        : 'Este é o seu ponto de partida';

  const subtitulo = !primeiraVez
    ? 'Você recebe os destaques dos temas marcados. Dá para mudar quando quiser.'
    : especialidade
      ? `Já deixamos marcado o que costuma importar em ${especialidade}. Tire o que não for seu, adicione o que faltar — e mude quando quiser.`
      : 'Já deixamos marcado um ponto de partida. Tire o que não for seu, adicione o que faltar — e mude quando quiser.';

  return (
    <div style={E.pagina}>
      <div style={E.caixa}>
        {/* Fixo, e não a especialidade: o chapéu diz ONDE a pessoa está no
            produto. Com o nome da especialidade ali, ele anunciava uma seção
            de conteúdo de cardiologia — mas esta tela é de configuração. E a
            especialidade já aparece no subtítulo, onde ela explica POR QUE
            aqueles temas vieram marcados. */}
        <span style={E.chapeu}>Notícias</span>
        <h1 style={E.titulo}>{titulo}</h1>
        <p style={E.subtitulo}>{subtitulo}</p>

        <ul style={E.grade}>
          {sugeridos.map((tema) => {
            const ativo = marcados.has(tema.id);
            return (
              <li key={tema.id}>
                <label
                  style={{ ...E.linha, opacity: ativo ? 1 : 0.55 }}
                  // Os títulos saíram da tela mas não do produto: quem quiser
                  // conferir o que o tema traz passa o mouse.
                  title={
                    tema.amostra.length
                      ? tema.amostra.join('\n')
                      : 'Nenhum destaque nos últimos 30 dias'
                  }
                >
                  <input
                    type="checkbox"
                    checked={ativo}
                    onChange={() => alternar(tema.id)}
                    style={E.check}
                  />
                  <span style={E.nome}>{tema.nome_pt}</span>
                  {/* O percentual só existe no modo social, onde ele É a
                      substância: "o que os colegas acompanham" sem número não
                      diz nada. Na curadoria não há número nenhum — a linha fica
                      sendo só o tema. */}
                  {social && tema.percentual !== null && (
                    <span style={E.conta}>{Math.round(tema.percentual * 100)}%</span>
                  )}
                </label>
              </li>
            );
          })}
        </ul>

        {!verTodos ? (
          <button type="button" onClick={() => setVerTodos(true)} style={E.linkOutros}>
            + Ver todos os {disponiveis.length} temas
          </button>
        ) : (
          <section style={E.blocoOutros}>
            <input
              type="search"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar tema — ex: coração, sepse, epilepsia…"
              style={E.campo}
            />
            <div style={E.chips}>
              {outros.map((t) => {
                const ativo = marcados.has(t.id);
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => alternar(t.id)}
                    aria-pressed={ativo}
                    style={{
                      ...E.chip,
                      background: ativo ? COR.tinta : 'transparent',
                      color: ativo ? COR.algodao : COR.petroleo,
                      borderColor: ativo ? COR.tinta : COR.linha,
                    }}
                  >
                    {ativo ? '✓ ' : ''}{t.nome_pt}
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {/* ── Palavras-chave ─────────────────────────────────────────────── */}
        <section style={E.blocoPalavras}>
          <h2 style={E.tituloSecao}>Acompanhar algo específico</h2>
          <p style={E.notaSecao}>
            Um assunto que não está na lista — uma droga, uma condição rara, uma técnica.
            Buscamos pelo texto dos destaques.
          </p>

          {palavras.length > 0 && (
            <div style={E.chips}>
              {palavras.map((p) => (
                <span key={p.termo} style={E.chipPalavra}>
                  {p.termo}
                  <span style={p.destaques ? E.palavraConta : E.palavraZero}>
                    {p.destaques === 0 ? 'nenhum destaque ainda' : `${p.destaques}`}
                  </span>
                  <button
                    type="button"
                    onClick={() => tirarPalavra(p.termo)}
                    style={E.tirar}
                    aria-label={`Remover ${p.termo}`}
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          )}

          <div style={E.linhaPalavra}>
            <input
              type="text"
              value={rascunho}
              onChange={(e) => setRascunho(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && acrescentarPalavra()}
              placeholder="ex: amiloidose cardíaca"
              style={{ ...E.campo, flex: 1 }}
            />
            <button
              type="button"
              onClick={acrescentarPalavra}
              disabled={salvandoPalavra || !rascunho.trim()}
              style={E.botaoAdd}
            >
              Adicionar
            </button>
          </div>

          {previa && (
            <p style={'erro' in previa ? E.previaErro : E.previa}>
              {'erro' in previa
                ? previa.erro
                : previa.destaques > 0
                  ? `→ ${previa.destaques} destaque${previa.destaques > 1 ? 's' : ''} nos últimos 30 dias`
                  : '→ nenhum destaque nos últimos 30 dias. Você pode adicionar mesmo assim — vale para o que vier.'}
            </p>
          )}
        </section>

        <label style={E.linhaEmail}>
          <input
            type="checkbox"
            checked={email}
            onChange={(e) => setEmail(e.target.checked)}
            style={E.checkbox}
          />
          <span>
            <strong style={{ color: COR.tinta }}>Me avise por e-mail quando houver novidade</strong>
            <br />
            <span style={E.notaEmail}>
              {agenda.frequencia === 'semanal'
                ? 'Um resumo por semana, e nenhum se nada casar com seus temas.'
                : 'No máximo um por dia, e nenhum nos dias em que nada casar com seus temas.'}
            </span>
          </span>
        </label>

        {/* Só com o e-mail ligado. Deixar o horário à mostra com o aviso
            desligado ofereceria uma escolha que não faz nada. */}
        {email && (
          <div style={E.agenda}>
            <div style={E.agendaLinha}>
              <span style={E.agendaRotulo}>Com que frequência</span>
              <div style={E.opcoes}>
                {(['diario', 'semanal'] as Frequencia[]).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => setAgenda((a) => ({ ...a, frequencia: f }))}
                    style={agenda.frequencia === f ? E.opcaoAtiva : E.opcao}
                  >
                    {f === 'diario' ? 'Todo dia' : 'Uma vez por semana'}
                  </button>
                ))}
              </div>
            </div>

            {/* O dia só existe no semanal — no diário seria uma pergunta sem
                resposta possível. */}
            {agenda.frequencia === 'semanal' && (
              <div style={E.agendaLinha}>
                <span style={E.agendaRotulo}>Em que dia</span>
                <div style={E.opcoes}>
                  {DIAS.map((nome, i) => (
                    <button
                      key={nome}
                      type="button"
                      onClick={() => setAgenda((a) => ({ ...a, dia_semana: i }))}
                      style={agenda.dia_semana === i ? E.opcaoAtiva : E.opcao}
                    >
                      {nome}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div style={E.agendaLinha}>
              <span style={E.agendaRotulo}>Em que horário</span>
              <div style={E.opcoes}>
                {FAIXAS.map(({ id, rotulo, hora }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setAgenda((a) => ({ ...a, faixa: id }))}
                    style={agenda.faixa === id ? E.opcaoAtiva : E.opcao}
                  >
                    {rotulo} <span style={E.hora}>{hora}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {marcados.size === 0 && palavras.length === 0 && (
          <p style={E.alerta}>
            Sem nenhum tema marcado, seu feed mostra os destaques gerais — sem filtro.
          </p>
        )}
        {erro && <p style={E.erro}>{erro}</p>}

        <div style={E.rodape}>
          <button type="button" onClick={salvar} disabled={salvando} style={E.botao}>
            {salvando ? 'Salvando…' : primeiraVez ? 'Começar a ler' : 'Salvar'}
          </button>
          {!primeiraVez && aoCancelar && (
            <button type="button" onClick={aoCancelar} style={E.botaoTexto}>
              Cancelar
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const E: Record<string, React.CSSProperties> = {
  pagina: {
    minHeight: '100vh',
    background: COR.algodao,
    padding: '40px 20px 64px',
    display: 'flex',
    justifyContent: 'center',
    fontFamily: FONTE,
  },
  centro: { padding: 64, textAlign: 'center', color: COR.petroleo, fontFamily: FONTE },
  caixa: { maxWidth: 640, width: '100%' },
  chapeu: {
    display: 'block',
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    color: COR.petroleo,
    opacity: 0.65,
    marginBottom: 6,
  },
  titulo: {
    fontSize: 27,
    lineHeight: 1.25,
    color: COR.tinta,
    margin: '0 0 8px',
    letterSpacing: '-0.01em',
  },
  subtitulo: { fontSize: 15, color: COR.petroleo, margin: '0 0 28px', lineHeight: 1.5 },

  // Duas colunas em tela larga, uma em telas estreitas — sem media query, que
  // não existe em estilo inline.
  grade: {
    listStyle: 'none',
    padding: 0,
    margin: '0 0 6px',
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
    columnGap: 18,
  },
  linha: {
    display: 'flex',
    alignItems: 'center',
    gap: 9,
    padding: '7px 0',
    cursor: 'pointer',
    transition: 'opacity .12s',
  },
  check: { width: 16, height: 16, flexShrink: 0, accentColor: COR.verde, cursor: 'pointer' },
  nome: {
    fontSize: 14,
    color: COR.tinta,
    flex: 1,
    minWidth: 0,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  conta: {
    fontSize: 11,
    fontWeight: 700,
    color: COR.petroleo,
    background: 'rgba(174,246,198,0.5)',
    padding: '1px 7px',
    borderRadius: 999,
    flexShrink: 0,
  },

  linkOutros: {
    background: 'none',
    border: 'none',
    padding: '14px 0',
    color: COR.petroleo,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: FONTE,
  },
  blocoOutros: { margin: '16px 0 8px' },
  chips: { display: 'flex', flexWrap: 'wrap', gap: 7, margin: '12px 0' },
  chip: {
    padding: '7px 13px',
    borderRadius: 999,
    border: '1px solid',
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: FONTE,
  },

  blocoPalavras: {
    marginTop: 28,
    padding: '18px 20px',
    background: 'rgba(174,246,198,0.18)',
    border: `1px solid ${COR.menta}`,
    borderRadius: 12,
  },
  tituloSecao: { fontSize: 15, fontWeight: 700, color: COR.tinta, margin: '0 0 4px' },
  notaSecao: { fontSize: 13, color: COR.petroleo, opacity: 0.8, margin: '0 0 12px', lineHeight: 1.45 },
  chipPalavra: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    padding: '6px 8px 6px 13px',
    borderRadius: 999,
    background: '#fff',
    border: `1px solid ${COR.linha}`,
    fontSize: 13,
    color: COR.tinta,
  },
  // Na grade de temas o zero e discreto (“—”); aqui ele e um ALERTA, porque a
  // pessoa acabou de cadastrar o termo e precisa saber que ele nao pega nada.
  palavraConta: { fontSize: 11, fontWeight: 700, color: COR.petroleo, opacity: 0.7 },
  palavraZero: { fontSize: 11, color: COR.aviso, background: COR.avisoFundo, padding: '1px 6px', borderRadius: 999 },
  tirar: {
    background: 'none',
    border: 'none',
    color: '#9aa8a5',
    cursor: 'pointer',
    fontSize: 12,
    padding: 2,
    lineHeight: 1,
  },
  linhaPalavra: { display: 'flex', gap: 8, alignItems: 'stretch' },
  campo: {
    width: '100%',
    padding: '10px 13px',
    border: `1px solid ${COR.linha}`,
    borderRadius: 9,
    fontSize: 14,
    color: COR.tinta,
    background: '#fff',
    outline: 'none',
    fontFamily: FONTE,
    boxSizing: 'border-box',
  },
  botaoAdd: {
    padding: '10px 18px',
    borderRadius: 9,
    border: 'none',
    background: COR.petroleo,
    color: COR.algodao,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    fontFamily: FONTE,
  },
  previa: { fontSize: 13, color: COR.petroleo, margin: '10px 0 0', lineHeight: 1.45 },
  previaErro: { fontSize: 13, color: COR.aviso, margin: '10px 0 0', lineHeight: 1.45 },

  linhaEmail: {
    display: 'flex',
    gap: 11,
    alignItems: 'flex-start',
    fontSize: 14,
    color: COR.petroleo,
    lineHeight: 1.5,
    cursor: 'pointer',
    margin: '26px 0 18px',
  },
  checkbox: { width: 17, height: 17, marginTop: 2, accentColor: COR.verde },
  notaEmail: { fontSize: 13, opacity: 0.8 },

  // Recuado e sobre fundo próprio: são ajustes DO aviso acima, não escolhas
  // soltas. O recuo alinha com o texto do checkbox, não com a caixa dele.
  agenda: {
    margin: '-6px 0 20px 28px',
    padding: '14px 16px',
    background: '#f2f7f4',
    borderRadius: 12,
    display: 'flex',
    flexDirection: 'column',
    gap: 13,
  },
  agendaLinha: { display: 'flex', flexDirection: 'column', gap: 7 },
  agendaRotulo: { fontSize: 13, fontWeight: 600, color: COR.petroleo },
  opcoes: { display: 'flex', flexWrap: 'wrap', gap: 7 },
  opcao: {
    padding: '7px 13px',
    borderRadius: 20,
    border: `1px solid ${COR.linha}`,
    background: '#fff',
    color: COR.petroleo,
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: FONTE,
  },
  opcaoAtiva: {
    padding: '7px 13px',
    borderRadius: 20,
    // A borda muda junto com o fundo: quem enxerga pouca cor continua vendo
    // qual está escolhido.
    border: `1px solid ${COR.petroleo}`,
    background: COR.menta,
    color: COR.tinta,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: FONTE,
  },
  hora: { opacity: 0.65, fontWeight: 400 },

  alerta: {
    fontSize: 13,
    color: '#6b4405',
    background: COR.avisoFundo,
    padding: '11px 14px',
    borderRadius: 10,
    lineHeight: 1.5,
  },
  erro: { fontSize: 14, color: '#a13a12' },
  rodape: { display: 'flex', alignItems: 'center', gap: 16, marginTop: 8 },
  botao: {
    padding: '13px 28px',
    borderRadius: 10,
    border: 'none',
    background: COR.tinta,
    color: COR.algodao,
    fontSize: 15,
    fontWeight: 700,
    cursor: 'pointer',
    fontFamily: FONTE,
  },
  botaoTexto: {
    background: 'none',
    border: 'none',
    color: COR.petroleo,
    fontSize: 14,
    cursor: 'pointer',
    fontFamily: FONTE,
    textDecoration: 'underline',
  },
};
