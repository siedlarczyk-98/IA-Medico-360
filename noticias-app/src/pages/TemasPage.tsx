/**
 * Escolha de temas — a primeira tela de quem abre o app.
 *
 * A lista NUNCA aparece em branco: os temas ligados à especialidade que o
 * usuário já informou no onboarding do app principal vêm pré-marcados. Quem não
 * tem especialidade registrada (o SSO de embed cria o usuário sem ela) cai no
 * conjunto generalista. Encarar 51 caixas vazias e ter que adivinhar o que
 * escolher seria a forma mais rápida de fazer alguém desistir.
 *
 * SOBRE "PALAVRAS-CHAVE"
 * O pedido original falava em palavras-chave livres. O que existe aqui é um
 * vocabulário CONTROLADO com busca por texto — o usuário digita "coração" e
 * filtra a lista, mas o que ele salva é sempre um tema do vocabulário.
 *
 * A diferença não é preciosismo: o tagger que classifica os artigos escolhe
 * desses mesmos slugs. Com palavra livre, "IC", "insuficiência cardíaca" e
 * "ICFEr" viram três coisas distintas, e o casamento entre o que o usuário
 * pediu e o que o artigo recebeu simplesmente não acontece. A busca dá a
 * sensação de campo livre sem quebrar o casamento.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  buscarMeusTemas,
  buscarPreferencias,
  salvarMeusTemas,
  salvarPreferencias,
  type Tema,
} from '../api/news';

const COLORS = {
  azulProfundo: '#0e252d',
  azulPetroleo: '#014751',
  verdeVibrante: '#00d17d',
  verdeMenta: '#aef6c6',
  algodao: '#fdfff4',
  linha: '#d9e6e2',
} as const;

const FONT = "var(--m360-font, 'Just Sans', -apple-system, 'Segoe UI', sans-serif)";

interface Props {
  /** Primeira visita muda o texto: é convite, não configuração. */
  primeiraVez: boolean;
  aoConcluir: () => void;
  aoCancelar?: () => void;
}

/** Ignora acento e caixa, para "cardiaca" achar "cardíaca". */
function normalizar(texto: string): string {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

export function TemasPage({ primeiraVez, aoConcluir, aoCancelar }: Props) {
  const [disponiveis, setDisponiveis] = useState<Tema[]>([]);
  const [sugeridos, setSugeridos] = useState<Set<string>>(new Set());
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [email, setEmail] = useState(false);
  const [busca, setBusca] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  useEffect(() => {
    let cancelado = false;

    async function carregar() {
      try {
        const [temas, prefs] = await Promise.all([buscarMeusTemas(), buscarPreferencias()]);
        if (cancelado) return;
        setDisponiveis(temas.disponiveis);
        setSugeridos(new Set(temas.sugeridos.map((t) => t.id)));
        // Já escolheu antes: respeita a escolha. Primeira vez: parte da sugestão.
        const base = temas.ja_escolheu ? temas.selecionados : temas.sugeridos;
        setMarcados(new Set(base.map((t) => t.id)));
        setEmail(prefs.email);
      } catch (e) {
        if (!cancelado) setErro(e instanceof Error ? e.message : 'Erro ao carregar temas');
      } finally {
        if (!cancelado) setCarregando(false);
      }
    }

    carregar();
    return () => {
      cancelado = true;
    };
  }, []);

  const [recomendados, outros] = useMemo(() => {
    const q = normalizar(busca.trim());
    const visiveis = q
      ? disponiveis.filter((t) => normalizar(t.nome_pt).includes(q))
      : disponiveis;
    return [
      visiveis.filter((t) => sugeridos.has(t.id)),
      visiveis.filter((t) => !sugeridos.has(t.id)),
    ];
  }, [disponiveis, sugeridos, busca]);

  function alternar(id: string) {
    setMarcados((atual) => {
      const novo = new Set(atual);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  }

  async function salvar() {
    setSalvando(true);
    setErro('');
    try {
      await salvarMeusTemas([...marcados]);
      await salvarPreferencias(email);
      aoConcluir();
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Erro ao salvar');
      setSalvando(false);
    }
  }

  if (carregando) {
    return <div style={estilos.centro}>Carregando temas…</div>;
  }

  const chip = (tema: Tema) => {
    const ativo = marcados.has(tema.id);
    return (
      <button
        key={tema.id}
        type="button"
        onClick={() => alternar(tema.id)}
        aria-pressed={ativo}
        style={{
          ...estilos.chip,
          background: ativo ? COLORS.azulProfundo : 'transparent',
          color: ativo ? COLORS.algodao : COLORS.azulPetroleo,
          borderColor: ativo ? COLORS.azulProfundo : COLORS.linha,
          fontWeight: ativo ? 700 : 500,
        }}
      >
        {ativo && <span style={estilos.check}>✓</span>}
        {tema.nome_pt}
      </button>
    );
  };

  return (
    <div style={estilos.pagina}>
      <div style={estilos.caixa}>
        <header style={estilos.cabecalho}>
          <h1 style={estilos.titulo}>
            {primeiraVez ? 'Sobre o que você quer saber?' : 'Seus temas'}
          </h1>
          <p style={estilos.subtitulo}>
            {primeiraVez
              ? 'Já marcamos os temas mais ligados à sua especialidade. Ajuste como quiser — você recebe só o que ficar marcado aqui.'
              : 'Você recebe destaques dos temas marcados. Pode mudar quando quiser.'}
          </p>
        </header>

        <div style={estilos.barraBusca}>
          <input
            type="search"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar tema — ex: coração, diabetes, sepse…"
            style={estilos.busca}
          />
          <span style={estilos.contador}>
            {marcados.size} {marcados.size === 1 ? 'tema' : 'temas'}
          </span>
        </div>

        {recomendados.length > 0 && (
          <section style={estilos.secao}>
            <h2 style={estilos.tituloSecao}>
              Sugeridos para você
              <span style={estilos.notaSecao}>com base na sua especialidade</span>
            </h2>
            <div style={estilos.grade}>{recomendados.map(chip)}</div>
          </section>
        )}

        {outros.length > 0 && (
          <section style={estilos.secao}>
            <h2 style={estilos.tituloSecao}>
              {recomendados.length > 0 ? 'Outros temas' : 'Temas'}
            </h2>
            <div style={estilos.grade}>{outros.map(chip)}</div>
          </section>
        )}

        {recomendados.length === 0 && outros.length === 0 && (
          <p style={estilos.semResultado}>
            Nenhum tema encontrado para “{busca}”. Os temas são uma lista fechada — se
            faltar algum que você precisa, vale nos dizer.
          </p>
        )}

        <section style={estilos.blocoEmail}>
          <label style={estilos.linhaEmail}>
            <input
              type="checkbox"
              checked={email}
              onChange={(e) => setEmail(e.target.checked)}
              style={estilos.checkbox}
            />
            <span>
              <strong style={{ color: COLORS.azulProfundo }}>
                Me avise por e-mail quando houver novidade
              </strong>
              <br />
              {/* Dizer isto aqui é o que separa a promessa deste produto de mais
                  uma newsletter: no dia em que nada casar, não chega nada. */}
              <span style={estilos.notaEmail}>
                No máximo um e-mail por dia, e nenhum nos dias em que nada casar com
                seus temas.
              </span>
            </span>
          </label>
        </section>

        {marcados.size === 0 && (
          <p style={estilos.aviso}>
            Sem nenhum tema marcado, seu feed mostra os destaques gerais — sem filtro.
          </p>
        )}

        {erro && <p style={estilos.erro}>{erro}</p>}

        <div style={estilos.rodape}>
          <button type="button" onClick={salvar} disabled={salvando} style={estilos.botao}>
            {salvando ? 'Salvando…' : primeiraVez ? 'Ver meus destaques' : 'Salvar'}
          </button>
          {!primeiraVez && aoCancelar && (
            <button type="button" onClick={aoCancelar} style={estilos.botaoTexto}>
              Cancelar
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const estilos: Record<string, React.CSSProperties> = {
  pagina: {
    minHeight: '100vh',
    background: COLORS.algodao,
    padding: '40px 20px 64px',
    display: 'flex',
    justifyContent: 'center',
    fontFamily: FONT,
  },
  centro: {
    padding: 64,
    textAlign: 'center',
    color: COLORS.azulPetroleo,
    fontFamily: FONT,
  },
  caixa: { maxWidth: 760, width: '100%' },
  cabecalho: { marginBottom: 24 },
  titulo: {
    fontSize: 30,
    lineHeight: 1.2,
    color: COLORS.azulProfundo,
    margin: '0 0 10px',
    letterSpacing: '-0.01em',
  },
  subtitulo: {
    fontSize: 15,
    color: COLORS.azulPetroleo,
    margin: 0,
    lineHeight: 1.55,
    maxWidth: 560,
  },
  barraBusca: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginBottom: 28,
  },
  busca: {
    flex: 1,
    padding: '11px 14px',
    border: `1px solid ${COLORS.linha}`,
    borderRadius: 10,
    fontSize: 14,
    color: COLORS.azulProfundo,
    background: '#fff',
    outline: 'none',
    fontFamily: FONT,
    boxSizing: 'border-box',
  },
  contador: {
    fontSize: 12,
    fontWeight: 700,
    color: COLORS.azulPetroleo,
    background: 'rgba(174,246,198,0.4)',
    padding: '7px 13px',
    borderRadius: 999,
    whiteSpace: 'nowrap',
  },
  secao: { marginBottom: 28 },
  tituloSecao: {
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.09em',
    textTransform: 'uppercase',
    color: COLORS.azulPetroleo,
    margin: '0 0 12px',
    display: 'flex',
    alignItems: 'baseline',
    gap: 8,
    flexWrap: 'wrap',
  },
  notaSecao: {
    fontSize: 11,
    fontWeight: 400,
    letterSpacing: 0,
    textTransform: 'none',
    opacity: 0.65,
  },
  grade: { display: 'flex', flexWrap: 'wrap', gap: 8 },
  chip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '9px 15px',
    borderRadius: 999,
    border: '1px solid',
    fontSize: 13.5,
    cursor: 'pointer',
    fontFamily: FONT,
    transition: 'background-color .12s, border-color .12s, color .12s',
  },
  check: { fontSize: 11, color: COLORS.verdeVibrante, fontWeight: 700 },
  blocoEmail: {
    background: 'rgba(174,246,198,0.22)',
    border: `1px solid ${COLORS.verdeMenta}`,
    borderRadius: 12,
    padding: '16px 18px',
    marginBottom: 20,
  },
  linhaEmail: {
    display: 'flex',
    gap: 12,
    alignItems: 'flex-start',
    fontSize: 14,
    color: COLORS.azulPetroleo,
    lineHeight: 1.5,
    cursor: 'pointer',
  },
  checkbox: { width: 17, height: 17, marginTop: 2, accentColor: COLORS.verdeVibrante },
  notaEmail: { fontSize: 13, opacity: 0.8 },
  semResultado: {
    fontSize: 14,
    color: COLORS.azulPetroleo,
    background: 'rgba(174,246,198,0.22)',
    padding: '14px 16px',
    borderRadius: 10,
    lineHeight: 1.5,
  },
  aviso: {
    fontSize: 13,
    color: '#6b4405',
    background: '#fdeccb',
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
    background: COLORS.azulProfundo,
    color: COLORS.algodao,
    fontSize: 15,
    fontWeight: 700,
    cursor: 'pointer',
    fontFamily: FONT,
  },
  botaoTexto: {
    background: 'none',
    border: 'none',
    color: COLORS.azulPetroleo,
    fontSize: 14,
    cursor: 'pointer',
    fontFamily: FONT,
    textDecoration: 'underline',
  },
};
