/**
 * HighlightsMagazine — a revista de destaques.
 * ---------------------------------------------------------------------------
 * O destaque de HOJE vira um "hero" editorial no topo; os demais aparecem como
 * lista compacta, com chips de journal como filtro rapido e busca por texto.
 *
 * FONTE DE DADOS: a API do proprio Medico 360 (`/api/v1/news/*`). O WordPress
 * saiu — o texto sempre esteve no nosso Postgres, e um CMS que serve a mesma
 * pagina para todos nao consegue entregar um feed personalizado por usuario.
 *
 * IDENTIDADE: JWT, obtido pelo SSO de embed em App.tsx. O `?email=` da URL e
 * apenas a semente dessa troca, nao a identidade em si.
 *
 * O HERO NUNCA E UM ITEM DE PREENCHIMENTO: dar destaque de capa a um item que
 * so entrou para a tela nao ficar vazia seria vende-lo como relevante quando
 * ele nao e.
 */
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import DOMPurify from "dompurify";
import { useFavorites } from "../hooks/useFavorites";
import { buscarArtigo, buscarFeed, naoInteressa, type Highlight, type MotivoVazio } from "../api/news";

const COLORS = {
  azulProfundo: "#0e252d",
  azulPetroleo: "#014751",
  verdeVibrante: "#00d17d",
  verdeMenta: "#aef6c6",
  algodao: "#fdfff4",
} as const;

const FONT_STACK = "var(--m360-font, 'Just Sans', -apple-system, 'Segoe UI', sans-serif)";

interface JournalMeta {
  slug: string;
  displayName: string;
  weekday: number; // 0=Domingo...6=Sábado (convenção JS Date.getDay())
  shortLabel: string;
  tagBg: string;
  tagText: string;
}

// Cores de badge próprias por journal — NÃO são os logos/cores oficiais das
// marcas (evita qualquer questão de uso de marca registrada), apenas uma
// paleta editorial nossa para diferenciar visualmente cada fonte.
const JOURNALS: JournalMeta[] = [
  { slug: "lancet", displayName: "The Lancet", weekday: 1, shortLabel: "Seg", tagBg: "#ffe1d6", tagText: "#a13a12" },
  { slug: "jama", displayName: "JAMA", weekday: 2, shortLabel: "Ter", tagBg: "#dce8fc", tagText: "#1a4a8a" },
  { slug: "nature_medicine", displayName: "Nature Medicine", weekday: 3, shortLabel: "Qua", tagBg: "#e3dbfa", tagText: "#4b2f96" },
  { slug: "nejm", displayName: "NEJM", weekday: 4, shortLabel: "Qui", tagBg: "#d6f0ea", tagText: "#0c5c4a" },
  { slug: "bmj", displayName: "The BMJ", weekday: 5, shortLabel: "Sex", tagBg: "#fdeccb", tagText: "#8a5a06" },
];

interface HighlightItem {
  articleId: number;
  title: string;
  resumo: string | null;
  sourceUrl: string | null;
  publishedAt: Date;
  journal: JournalMeta | null;
  /** Temas do usuario que casaram — o "por que estou vendo isto?" do card. */
  temas: { slug: string; nome: string }[];
  /** Palavras-chave do usuario que casaram com o TEXTO. Eixo separado dos temas. */
  palavras: string[];
  /**
   * Entrou so para a tela nao ficar vazia (tema adjacente a especialidade).
   * Precisa ser exibido COMO TAL: e a diferenca entre o usuario confiar e nao
   * confiar no filtro. O digest ignora estes itens.
   */
  preenchimento: boolean;
}

function journalBySlug(slug: string | undefined): JournalMeta | null {
  return JOURNALS.find((j) => j.slug === slug) ?? null;
}

function paraItem(h: Highlight): HighlightItem {
  return {
    articleId: h.id,
    title: h.rewritten_title ?? "(sem titulo)",
    resumo: h.resumo,
    sourceUrl: h.source_url,
    publishedAt: new Date(h.visible_at ?? h.published_date ?? Date.now()),
    journal: journalBySlug(h.journal_slug),
    temas: h.temas.map((t) => ({ slug: t.slug, nome: t.nome_pt })),
    palavras: h.palavras,
    preenchimento: h.preenchimento,
  };
}

/**
 * Carrega o feed da nossa API.
 *
 * Antes eram DUAS chamadas — os posts do WordPress e a nossa lista — casadas
 * pela URL do post. O WordPress saiu: o texto sempre esteve no nosso Postgres, e
 * um CMS que serve a mesma pagina para todos nao consegue entregar feed
 * personalizado. Isto aqui e o que sobrou, e e menos codigo do que havia.
 */
function useHighlights(todos: boolean, perPage = 30) {
  const [items, setItems] = useState<HighlightItem[]>([]);
  const [motivoVazio, setMotivoVazio] = useState<MotivoVazio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    // O `setLoading(true)` mora DENTRO da funcao async, e nao no corpo do
    // efeito: chamar setState de forma sincrona ali dispara um render em
    // cascata antes mesmo de a busca comecar.
    async function carregar() {
      setLoading(true);
      setError(null);
      try {
        const feed = await buscarFeed(perPage, todos);
        if (cancelled) return;
        setItems(feed.itens.map(paraItem));
        setMotivoVazio(feed.motivo_vazio);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Erro ao carregar destaques");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    carregar();
    return () => {
      cancelled = true;
    };
  }, [todos, perPage]);

  return { items, motivoVazio, loading, error };
}

export interface HighlightsMagazineProps {
  /** Abre a tela de temas. O feed sem saida para editar a selecao vira caixa-preta. */
  aoEditarTemas: () => void;
  perPage?: number;
}

const MENSAGEM_VAZIO: Record<MotivoVazio, { titulo: string; texto: string }> = {
  // Os dois casos SAO diferentes e precisam ser ditos de forma diferente. Uma
  // tela vazia ambigua faz o usuario concluir que o produto morreu.
  sem_conteudo: {
    titulo: "Nenhum destaque novo por enquanto",
    texto: "Os journals publicam de segunda a sexta. Volte amanha.",
  },
  sem_match: {
    titulo: "Nada novo nos seus temas",
    texto: "Ha destaques publicados, mas nenhum casou com o que voce escolheu. Abaixo, o que mais se aproxima.",
  },
};

export default function HighlightsMagazine({ aoEditarTemas, perPage = 30 }: HighlightsMagazineProps) {
  const [verTudo, setVerTudo] = useState(false);
  const { items, motivoVazio, loading, error } = useHighlights(verTudo, perPage);
  const { favoriteIds, toggleFavorite, canFavorite } = useFavorites();

  const [searchQuery, setSearchQuery] = useState("");
  const [activeDayFilter, setActiveDayFilter] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<HighlightItem | null>(null);
  const [ocultados, setOcultados] = useState<Set<number>>(new Set());

  const todayWeekday = new Date().getDay();
  const todayJournalSlug = JOURNALS.find((j) => j.weekday === todayWeekday)?.slug ?? null;

  const visiveis = useMemo(
    () => items.filter((i) => !ocultados.has(i.articleId)),
    [items, ocultados]
  );

  // O hero so pode ser um item que casou de verdade: dar destaque de capa a um
  // item de preenchimento seria vende-lo como relevante quando ele nao e.
  const heroItem = useMemo(() => {
    const candidatos = visiveis.filter((i) => !i.preenchimento);
    if (!candidatos.length) return null;
    if (!todayJournalSlug) return candidatos[0];
    return candidatos.find((i) => i.journal?.slug === todayJournalSlug) ?? candidatos[0];
  }, [visiveis, todayJournalSlug]);

  const filteredItems = useMemo(() => {
    let list = activeDayFilter ? visiveis : visiveis.filter((i) => i.articleId !== heroItem?.articleId);

    if (activeDayFilter === "favorites") {
      list = list.filter((i) => favoriteIds.has(i.articleId));
    } else if (activeDayFilter) {
      list = list.filter((i) => i.journal?.slug === activeDayFilter);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter((i) => i.title.toLowerCase().includes(q) || (i.resumo ?? "").toLowerCase().includes(q));
    }

    return list;
  }, [visiveis, heroItem, activeDayFilter, searchQuery, favoriteIds]);

  async function marcarNaoInteressa(item: HighlightItem) {
    // Some da tela na hora; o registro no servidor e o que permite corrigir a
    // taxonomia depois com dado real em vez de palpite.
    setOcultados((atual) => new Set(atual).add(item.articleId));
    try {
      await naoInteressa(item.articleId, item.temas[0]?.slug);
    } catch {
      // Falhar aqui nao devolve o card para a tela: o usuario ja disse que nao
      // quer ve-lo, e reaparecer seria pior que perder o registro.
    }
  }

  const aviso = motivoVazio ? MENSAGEM_VAZIO[motivoVazio] : null;

  return (
    <div style={styles.page}>
      <TopBar verTudo={verTudo} onVerTudo={setVerTudo} aoEditarTemas={aoEditarTemas} />

      {aviso && !loading && (
        <div style={styles.avisoVazio}>
          <strong style={{ display: "block", marginBottom: 4 }}>{aviso.titulo}</strong>
          <span>{aviso.texto}</span>
          <button type="button" onClick={aoEditarTemas} style={styles.linkTemas}>
            Ajustar meus temas
          </button>
        </div>
      )}

      {heroItem && (
        <Hero
          item={heroItem}
          onOpen={() => setSelectedItem(heroItem)}
          isFavorited={favoriteIds.has(heroItem.articleId)}
          canFavorite={canFavorite}
          onToggleFavorite={() => toggleFavorite(heroItem.articleId)}
        />
      )}

      <Toolbar
        activeFilter={activeDayFilter}
        onFilterChange={setActiveDayFilter}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        todayJournalSlug={todayJournalSlug}
      />

      <div style={styles.list}>
        {loading && <StatusMessage text="Carregando destaques..." />}
        {error && <StatusMessage text={`Nao foi possivel carregar agora. (${error})`} isError />}
        {!loading && !error && filteredItems.length === 0 && !aviso && (
          <StatusMessage
            text={
              activeDayFilter === "favorites"
                ? "Voce ainda nao favoritou nenhum destaque."
                : "Nenhum destaque encontrado para esse filtro."
            }
          />
        )}
        {!loading &&
          !error &&
          filteredItems.map((item) => (
            <ListRow
              key={item.articleId}
              item={item}
              onOpen={() => setSelectedItem(item)}
              isFavorited={favoriteIds.has(item.articleId)}
              canFavorite={canFavorite}
              onToggleFavorite={() => toggleFavorite(item.articleId)}
              onNaoInteressa={() => marcarNaoInteressa(item)}
            />
          ))}
      </div>

      {selectedItem && <DetailModal item={selectedItem} onClose={() => setSelectedItem(null)} />}
    </div>
  );
}

/**
 * Barra de escopo do feed.
 *
 * "Para voce" e "Tudo" sao o MESMO eixo — o que a lista esta mostrando — entao
 * viram um seletor segmentado, e nao dois botoes soltos: um controle so, com
 * uma metade acesa, deixa obvio que sao alternativas excludentes.
 *
 * "Editar temas" e outro eixo (configuracao, nao filtragem) e por isso fica
 * separado, do outro lado. A versao anterior empilhava os tres como pilulas
 * iguais numa fileira propria, o que sugeria que eram tres filtros irmaos dos
 * chips de journal logo acima.
 *
 * "Tudo" e a valvula de escape do filtro: sem ela, a primeira reclamacao e
 * "sumiu conteudo" e o usuario nao tem como verificar.
 */
function TopBar({
  verTudo,
  onVerTudo,
  aoEditarTemas,
}: {
  verTudo: boolean;
  onVerTudo: (v: boolean) => void;
  aoEditarTemas: () => void;
}) {
  return (
    <div style={styles.topBar}>
      <div style={styles.segmentado} role="tablist" aria-label="Escopo do feed">
        {[
          { rotulo: "Para voce", ativo: !verTudo, valor: false },
          { rotulo: "Tudo", ativo: verTudo, valor: true },
        ].map((op) => (
          <button
            key={op.rotulo}
            type="button"
            role="tab"
            aria-selected={op.ativo}
            onClick={() => onVerTudo(op.valor)}
            style={{ ...styles.segItem, ...(op.ativo ? styles.segItemAtivo : {}) }}
          >
            {op.rotulo}
          </button>
        ))}
      </div>
      <button type="button" onClick={aoEditarTemas} style={styles.acaoTemas}>
        Editar meus temas
      </button>
    </div>
  );
}

/**
 * Etiqueta dos temas que casaram, ou o aviso de preenchimento.
 *
 * Responde "por que estou vendo isto?" — o que torna o filtro confiavel e o que
 * permite depurar a taxonomia com base em reclamacao real.
 */
function Temas({ item, sobreEscuro = false }: { item: HighlightItem; sobreEscuro?: boolean }) {
  if (item.preenchimento) {
    return <span style={styles.tagPreenchimento}>fora dos seus temas</span>;
  }
  // Palavra-chave e tema sao EIXOS diferentes e por isso aparecem diferentes: o
  // primeiro e um termo que a pessoa escolheu a dedo e casa com o texto do
  // artigo; o segundo veio do tagger. Misturar os dois numa etiqueta so
  // esconderia justamente a informacao que responde "por que estou vendo isto?".
  if (!item.temas.length && !item.palavras.length) return null;
  return (
    <span style={styles.linhaEtiquetas}>
      {item.palavras.map((p) => (
        <span key={p} style={styles.tagPalavra}>
          {p} · sua palavra-chave
        </span>
      ))}
      {item.temas.length > 0 && (
        // O hero tem fundo em degrade escuro; a cor padrao da etiqueta (azul
        // petroleo) fica ilegivel ali. Uma variante clara, e nao uma cor unica
        // de compromisso que ficaria fraca nos dois lugares.
        <span style={sobreEscuro ? styles.tagTemasClaro : styles.tagTemas}>
          {item.temas.slice(0, 3).map((t) => t.nome).join(" · ")}
        </span>
      )}
    </span>
  );
}

function Hero({
  item,
  onOpen,
  isFavorited,
  canFavorite,
  onToggleFavorite,
}: {
  item: HighlightItem;
  onOpen: () => void;
  isFavorited: boolean;
  canFavorite: boolean;
  onToggleFavorite: () => void;
}) {
  return (
    <div style={styles.hero}>
      <div style={styles.heroDecoration} />
      <span style={styles.heroEyebrow}>Destaque de hoje{item.journal ? ` · ${item.journal.displayName}` : ""}</span>
      <h1 style={styles.heroTitle}>{item.title}</h1>
      <p style={styles.heroExcerpt}>{item.resumo ?? ""}</p>
      <Temas item={item} sobreEscuro />
      <div style={styles.heroActions}>
        <button type="button" onClick={onOpen} style={styles.heroCta}>
          Ler o destaque completo →
        </button>
        {canFavorite && (
          <button type="button" onClick={onToggleFavorite} style={styles.heroFavButton} aria-label="Favoritar">
            {isFavorited ? "♥ Favoritado" : "♡ Favoritar"}
          </button>
        )}
      </div>
    </div>
  );
}

function Toolbar({
  activeFilter,
  onFilterChange,
  searchQuery,
  onSearchChange,
  todayJournalSlug,
}: {
  activeFilter: string | null;
  onFilterChange: (v: string | null) => void;
  searchQuery: string;
  onSearchChange: (v: string) => void;
  todayJournalSlug: string | null;
}) {
  return (
    <div style={styles.toolbar}>
      <div style={styles.dayChips}>
        {JOURNALS.map((j) => (
          <button
            key={j.slug}
            type="button"
            onClick={() => onFilterChange(activeFilter === j.slug ? null : j.slug)}
            style={{
              ...styles.dayChip,
              ...(activeFilter === j.slug ? styles.dayChipActive : {}),
              ...(j.slug === todayJournalSlug && activeFilter !== j.slug ? styles.dayChipToday : {}),
            }}
          >
            {j.shortLabel} · {j.displayName}
          </button>
        ))}
        <button
          type="button"
          onClick={() => onFilterChange(activeFilter === "favorites" ? null : "favorites")}
          style={{ ...styles.dayChip, ...(activeFilter === "favorites" ? styles.dayChipActive : {}) }}
        >
          ♥ Favoritos
        </button>
      </div>
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Buscar por tema, journal..."
        style={styles.searchInput}
      />
    </div>
  );
}

function ListRow({
  item,
  onOpen,
  isFavorited,
  canFavorite,
  onToggleFavorite,
  onNaoInteressa,
}: {
  item: HighlightItem;
  onOpen: () => void;
  isFavorited: boolean;
  canFavorite: boolean;
  onToggleFavorite: () => void;
  onNaoInteressa: () => void;
}) {
  const day = item.publishedAt.getDate().toString().padStart(2, "0");
  const month = item.publishedAt.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "").toUpperCase();

  return (
    <div style={styles.row}>
      <div style={styles.rowDate}>
        <span style={styles.rowDateDay}>{day}</span>
        {month}
      </div>
      <button type="button" onClick={onOpen} style={styles.rowMain}>
        <div style={styles.rowTitle}>{item.title}</div>
        <div style={styles.rowExcerpt}>
          {item.journal && <span style={{ ...styles.rowJournalTag, backgroundColor: item.journal.tagBg, color: item.journal.tagText }}>{item.journal.displayName}</span>}
          {" "}
          {(item.resumo ?? "").slice(0, 110)}
        </div>
        <Temas item={item} />
      </button>
      <div style={styles.rowAcoes}>
        {canFavorite && (
          <button type="button" onClick={onToggleFavorite} style={styles.rowFavButton} aria-label="Favoritar">
            {isFavorited ? "♥" : "♡"}
          </button>
        )}
        {/* Uma tabela e um botao, e a unica fonte de dado real para corrigir o
            mapeamento tema<->especialidade depois. */}
        <button
          type="button"
          onClick={onNaoInteressa}
          style={styles.rowDispensar}
          title="Nao e do meu interesse"
          aria-label="Nao e do meu interesse"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

function DetailModal({ item, onClose }: { item: HighlightItem; onClose: () => void }) {
  // O corpo e buscado ao abrir, e nao junto da listagem: ele responde por ~80%
  // do payload e so um card por vez e lido. Antes vinha do WordPress; agora sai
  // do mesmo Postgres onde o redator o escreveu.
  const [corpo, setCorpo] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    let cancelado = false;
    buscarArtigo(item.articleId)
      .then((a) => {
        if (!cancelado) setCorpo(a.rewritten_body ?? "");
      })
      .catch((e) => {
        if (!cancelado) setErro(e instanceof Error ? e.message : "Erro ao carregar");
      });
    return () => {
      cancelado = true;
    };
  }, [item.articleId]);

  return (
    <div style={styles.modalOverlay} onClick={onClose}>
      <div style={styles.modalContent} onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={onClose} style={styles.modalCloseButton} aria-label="Fechar">
          ✕
        </button>
        {item.journal && (
          <span style={{ ...styles.rowJournalTag, backgroundColor: item.journal.tagBg, color: item.journal.tagText }}>
            {item.journal.displayName}
          </span>
        )}
        <h3 style={styles.modalTitle}>{item.title}</h3>
        <span style={styles.modalDate}>
          {item.publishedAt.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" })}
        </span>
        <Temas item={item} />
        {corpo === null && !erro && <p style={styles.statusMessage}>Carregando...</p>}
        {erro && <p style={{ ...styles.statusMessage, ...styles.statusMessageError }}>{erro}</p>}
        {corpo !== null && (
          // O corpo e gerado pelo nosso redator, mas passa pelo DOMPurify assim
          // mesmo: conteudo que vira HTML na tela nunca deve depender de a fonte
          // ser confiavel hoje.
          <div style={styles.modalBody} dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(corpo) }} />
        )}
        {item.sourceUrl && (
          <a href={item.sourceUrl} target="_blank" rel="noopener noreferrer" style={styles.modalSourceLink}>
            Ver publicacao original ↗
          </a>
        )}
      </div>
    </div>
  );
}

function StatusMessage({ text, isError = false }: { text: string; isError?: boolean }) {
  return <p style={{ ...styles.statusMessage, ...(isError ? styles.statusMessageError : {}) }}>{text}</p>;
}

const styles: Record<string, CSSProperties> = {
  avisoVazio: {
    background: "#fdeccb",
    color: "#6b4405",
    borderRadius: 12,
    padding: "14px 16px",
    marginBottom: 20,
    fontSize: 14,
    lineHeight: 1.5,
  },
  linkTemas: {
    display: "block",
    marginTop: 8,
    background: "none",
    border: "none",
    padding: 0,
    color: "#014751",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
    textDecoration: "underline",
  },
  topBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
    padding: "14px 40px",
    borderBottom: `1px solid ${COLORS.verdeMenta}`,
  },
  segmentado: {
    display: "inline-flex",
    padding: 3,
    gap: 2,
    borderRadius: 999,
    backgroundColor: "rgba(174,246,198,0.35)",
  },
  segItem: {
    padding: "6px 18px",
    borderRadius: 999,
    border: "none",
    background: "transparent",
    color: COLORS.azulPetroleo,
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    fontFamily: FONT_STACK,
    transition: "background-color .12s, color .12s",
  },
  segItemAtivo: {
    backgroundColor: COLORS.azulProfundo,
    color: COLORS.algodao,
  },
  acaoTemas: {
    padding: "6px 14px",
    borderRadius: 999,
    border: `1px solid ${COLORS.verdeMenta}`,
    background: "transparent",
    color: COLORS.azulPetroleo,
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: FONT_STACK,
  },
  tagTemas: {
    display: "inline-block",
    marginTop: 6,
    fontSize: 12,
    color: "#014751",
    opacity: 0.8,
  },
  linhaEtiquetas: { display: "flex", flexWrap: "wrap" as const, gap: 6, alignItems: "center" },
  tagPalavra: {
    display: "inline-block",
    marginTop: 6,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.02em",
    color: "#4b2f96",
    background: "#e3dbfa",
    padding: "2px 9px",
    borderRadius: 999,
  },
  tagTemasClaro: {
    display: "block",
    marginBottom: 16,
    fontSize: 12,
    letterSpacing: "0.02em",
    color: "#aef6c6",
  },
  tagPreenchimento: {
    display: "inline-block",
    marginTop: 6,
    fontSize: 11,
    letterSpacing: "0.04em",
    textTransform: "uppercase" as const,
    color: "#8a5a06",
    background: "#fdeccb",
    padding: "2px 8px",
    borderRadius: 999,
  },
  rowAcoes: { display: "flex", flexDirection: "column" as const, gap: 4, alignItems: "center" },
  rowDispensar: {
    background: "none",
    border: "none",
    color: "#9aa8a5",
    fontSize: 13,
    cursor: "pointer",
    lineHeight: 1,
    padding: 4,
  },
  page: {
    fontFamily: FONT_STACK,
    backgroundColor: COLORS.algodao,
    color: COLORS.azulProfundo,
    minHeight: "100vh",
  },
  hero: {
    position: "relative",
    padding: "48px 40px",
    background: `linear-gradient(135deg, ${COLORS.azulProfundo} 0%, ${COLORS.azulPetroleo} 100%)`,
    color: COLORS.algodao,
    overflow: "hidden",
  },
  heroDecoration: {
    position: "absolute",
    right: -60,
    top: -60,
    width: 240,
    height: 240,
    borderRadius: "50%",
    backgroundColor: "rgba(0,209,125,0.15)",
  },
  heroEyebrow: {
    display: "block",
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: 1.5,
    textTransform: "uppercase",
    color: COLORS.verdeMenta,
    marginBottom: 12,
    position: "relative",
  },
  heroTitle: {
    fontSize: 30,
    fontWeight: 700,
    maxWidth: 560,
    lineHeight: 1.3,
    marginBottom: 12,
    position: "relative",
  },
  heroExcerpt: {
    fontSize: 14,
    color: "rgba(253,255,244,0.8)",
    maxWidth: 520,
    lineHeight: 1.6,
    marginBottom: 20,
    position: "relative",
  },
  heroActions: {
    display: "flex",
    gap: 12,
    alignItems: "center",
    position: "relative",
  },
  heroCta: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    backgroundColor: COLORS.verdeVibrante,
    color: COLORS.azulProfundo,
    fontWeight: 700,
    fontSize: 13,
    padding: "10px 20px",
    borderRadius: 10,
    border: "none",
    cursor: "pointer",
    fontFamily: FONT_STACK,
  },
  heroFavButton: {
    backgroundColor: "transparent",
    border: `1px solid ${COLORS.verdeMenta}`,
    color: COLORS.algodao,
    fontSize: 13,
    fontWeight: 700,
    padding: "10px 16px",
    borderRadius: 10,
    cursor: "pointer",
    fontFamily: FONT_STACK,
  },
  toolbar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "20px 40px",
    borderBottom: `1px solid ${COLORS.verdeMenta}`,
    flexWrap: "wrap",
    gap: 12,
  },
  dayChips: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
  },
  dayChip: {
    fontSize: 11,
    fontWeight: 700,
    padding: "6px 12px",
    borderRadius: 999,
    border: `1px solid ${COLORS.verdeMenta}`,
    color: COLORS.azulPetroleo,
    backgroundColor: "transparent",
    cursor: "pointer",
    fontFamily: FONT_STACK,
  },
  dayChipActive: {
    backgroundColor: COLORS.azulProfundo,
    color: COLORS.algodao,
    borderColor: COLORS.azulProfundo,
  },
  dayChipToday: {
    borderColor: COLORS.verdeVibrante,
    borderWidth: 2,
  },
  searchInput: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    backgroundColor: "#ffffff",
    border: `1px solid ${COLORS.verdeMenta}`,
    borderRadius: 10,
    padding: "8px 14px",
    fontSize: 13,
    color: COLORS.azulPetroleo,
    fontFamily: FONT_STACK,
    minWidth: 220,
  },
  list: {
    padding: "24px 40px 40px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  row: {
    display: "grid",
    gridTemplateColumns: "70px 1fr auto",
    gap: 20,
    alignItems: "center",
    padding: "14px 12px",
    borderRadius: 12,
  },
  rowDate: {
    fontSize: 11,
    fontWeight: 700,
    color: COLORS.azulPetroleo,
    textAlign: "center",
  },
  rowDateDay: {
    fontSize: 20,
    color: COLORS.azulProfundo,
    display: "block",
  },
  rowMain: {
    textAlign: "left",
    background: "transparent",
    border: "none",
    cursor: "pointer",
    padding: 0,
    fontFamily: FONT_STACK,
  },
  rowTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: COLORS.azulProfundo,
    marginBottom: 4,
  },
  rowExcerpt: {
    fontSize: 12.5,
    color: COLORS.azulPetroleo,
  },
  rowJournalTag: {
    display: "inline-block",
    fontSize: 10,
    fontWeight: 800,
    padding: "2px 8px",
    borderRadius: 999,
    textTransform: "uppercase",
    letterSpacing: 0.3,
    marginRight: 6,
  },
  rowFavButton: {
    background: "transparent",
    border: "none",
    fontSize: 18,
    cursor: "pointer",
    color: COLORS.verdeVibrante,
  },
  statusMessage: {
    fontSize: 14,
    color: COLORS.azulPetroleo,
    padding: "24px 0",
    textAlign: "center",
  },
  statusMessageError: {
    color: "#b3261e",
  },
  modalOverlay: {
    position: "fixed",
    inset: 0,
    backgroundColor: "rgba(14, 37, 45, 0.6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    padding: 24,
  },
  modalContent: {
    backgroundColor: COLORS.algodao,
    borderRadius: 20,
    padding: 32,
    maxWidth: 680,
    width: "100%",
    maxHeight: "85vh",
    overflowY: "auto",
    position: "relative",
    fontFamily: FONT_STACK,
    color: COLORS.azulProfundo,
  },
  modalCloseButton: {
    position: "absolute",
    top: 16,
    right: 16,
    border: "none",
    backgroundColor: "transparent",
    fontSize: 18,
    cursor: "pointer",
    color: COLORS.azulPetroleo,
  },
  modalTitle: {
    fontSize: 22,
    fontWeight: 700,
    marginTop: 12,
    marginBottom: 4,
    lineHeight: 1.3,
  },
  modalDate: {
    fontSize: 11,
    color: COLORS.azulPetroleo,
    opacity: 0.7,
  },
  modalBody: {
    marginTop: 20,
    fontSize: 15,
    lineHeight: 1.7,
    color: COLORS.azulProfundo,
  },
  modalSourceLink: {
    display: "inline-block",
    marginTop: 24,
    fontSize: 13,
    fontWeight: 700,
    color: COLORS.verdeVibrante,
    textDecoration: "none",
  },
};
