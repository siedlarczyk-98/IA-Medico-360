/**
 * Escolha de temas — a primeira tela de quem abre o app pela primeira vez.
 *
 * A lista NUNCA aparece vazia: os temas `core` e `relevante` da especialidade
 * que o usuário já informou no onboarding vêm pré-marcados. Ele desmarca o que
 * não quiser e acrescenta o que faltar. Encarar 50 caixas em branco e ter que
 * adivinhar o que escolher seria a forma mais rápida de fazê-lo desistir.
 */
import { useEffect, useState } from 'react';
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
  algodao: '#fdfff4',
} as const;

interface Props {
  /** Primeira visita muda o texto: é convite, não configuração. */
  primeiraVez: boolean;
  aoConcluir: () => void;
}

export function TemasPage({ primeiraVez, aoConcluir }: Props) {
  const [disponiveis, setDisponiveis] = useState<Tema[]>([]);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [email, setEmail] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');

  useEffect(() => {
    Promise.all([buscarMeusTemas(), buscarPreferencias()])
      .then(([temas, prefs]) => {
        setDisponiveis(temas.disponiveis);
        // Já escolheu antes: respeita a escolha. Primeira vez: usa a sugestão
        // derivada da especialidade.
        const base = temas.ja_escolheu ? temas.selecionados : temas.sugeridos;
        setMarcados(new Set(base.map((t) => t.id)));
        setEmail(prefs.email);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : 'Erro ao carregar temas'))
      .finally(() => setCarregando(false));
  }, []);

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
    } finally {
      setSalvando(false);
    }
  }

  if (carregando) {
    return <div style={estilos.centro}>Carregando temas…</div>;
  }

  return (
    <div style={estilos.pagina}>
      <div style={estilos.caixa}>
        <h1 style={estilos.titulo}>
          {primeiraVez ? 'Sobre o que você quer saber?' : 'Seus temas'}
        </h1>
        <p style={estilos.subtitulo}>
          {primeiraVez
            ? 'Marcamos os temas mais ligados à sua especialidade. Ajuste como quiser — você recebe só o que escolher aqui.'
            : 'Você recebe destaques dos temas marcados. Pode mudar quando quiser.'}
        </p>

        <div style={estilos.grade}>
          {disponiveis.map((tema) => {
            const ativo = marcados.has(tema.id);
            return (
              <button
                key={tema.id}
                type="button"
                onClick={() => alternar(tema.id)}
                aria-pressed={ativo}
                style={{
                  ...estilos.chip,
                  background: ativo ? COLORS.verdeVibrante : 'transparent',
                  color: ativo ? COLORS.azulProfundo : COLORS.azulPetroleo,
                  borderColor: ativo ? COLORS.verdeVibrante : '#cbd8d5',
                  fontWeight: ativo ? 600 : 400,
                }}
              >
                {tema.nome_pt}
              </button>
            );
          })}
        </div>

        <label style={estilos.linhaEmail}>
          <input
            type="checkbox"
            checked={email}
            onChange={(e) => setEmail(e.target.checked)}
            style={{ width: 16, height: 16 }}
          />
          <span>
            Quero receber um e-mail quando houver novidade nos meus temas.
            <br />
            {/* Dizer isto na tela é o que diferencia a promessa do produto de
                mais uma newsletter: no dia em que nada casar, não chega nada. */}
            <span style={estilos.notaEmail}>
              No máximo um por dia, e nenhum nos dias em que nada casar com seus temas.
            </span>
          </span>
        </label>

        {marcados.size === 0 && (
          <p style={estilos.aviso}>
            Sem nenhum tema marcado, seu feed vai mostrar os destaques gerais.
          </p>
        )}

        {erro && <p style={estilos.erro}>{erro}</p>}

        <button type="button" onClick={salvar} disabled={salvando} style={estilos.botao}>
          {salvando ? 'Salvando…' : primeiraVez ? 'Ver meus destaques' : 'Salvar'}
        </button>
      </div>
    </div>
  );
}

const estilos: Record<string, React.CSSProperties> = {
  pagina: {
    minHeight: '100vh',
    background: COLORS.algodao,
    padding: '32px 16px',
    display: 'flex',
    justifyContent: 'center',
  },
  centro: { padding: 48, textAlign: 'center', color: COLORS.azulPetroleo },
  caixa: { maxWidth: 720, width: '100%' },
  titulo: { fontSize: 28, color: COLORS.azulProfundo, margin: '0 0 8px' },
  subtitulo: { fontSize: 15, color: COLORS.azulPetroleo, margin: '0 0 24px', lineHeight: 1.5 },
  grade: { display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 28 },
  chip: {
    padding: '8px 14px',
    borderRadius: 999,
    border: '1px solid',
    fontSize: 14,
    cursor: 'pointer',
    transition: 'all .12s',
  },
  linhaEmail: {
    display: 'flex',
    gap: 10,
    alignItems: 'flex-start',
    fontSize: 14,
    color: COLORS.azulPetroleo,
    lineHeight: 1.5,
    marginBottom: 20,
    cursor: 'pointer',
  },
  notaEmail: { fontSize: 13, opacity: 0.75 },
  aviso: { fontSize: 13, color: '#8a5a06', background: '#fdeccb', padding: '10px 12px', borderRadius: 8 },
  erro: { fontSize: 14, color: '#a13a12' },
  botao: {
    padding: '12px 24px',
    borderRadius: 10,
    border: 'none',
    background: COLORS.azulPetroleo,
    color: COLORS.algodao,
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
  },
};
