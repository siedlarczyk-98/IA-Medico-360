/**
 * Histórico e Pastas: o conteúdo, sem o recipiente.
 *
 * Dentro da Waid ele mora numa gaveta (o hospedeiro já tem barra de abas);
 * fora dela, numa tela por cima da Consulta, aberta pela barra de abas. O que
 * muda entre os dois é só o `topo` e o `rodape` que o recipiente passa — lista,
 * seleção, pasta aberta e folhas são as mesmas.
 *
 * Tudo que abre por cima (pasta, seleção, folhas) é camada: o botão voltar do
 * Android fecha a de cima. Ver `camadas.ts`.
 */

import { useMemo, type ReactNode } from 'react';

import type { ConversationSummary } from '../../api/conversations';
import type { Folder } from '../../api/folders';
import type { ChatController } from '../../chat/useChatController';
import type { useConversasEPastas } from '../../hooks/useConversasEPastas';
import { agruparConversas, tituloDe } from './agruparConversas';
import { Icone } from './Icone';
import { ItemConversa } from './ItemConversa';
import { SheetAcoes, SheetMover, SheetRenomear } from './SheetsDeConversa';
import { SheetPasta } from './SheetPasta';
import { useCamada } from './useCamada';

export type Aba = 'historico' | 'pastas';

type Folha =
  | { tipo: 'acoes'; conversa: ConversationSummary }
  | { tipo: 'mover'; ids: string[]; pastaAtual?: string | null }
  | { tipo: 'renomear'; conversa: ConversationSummary }
  | { tipo: 'pasta'; pasta?: Folder };

interface Props {
  aba: Aba;
  chat: ChatController;
  dados: ReturnType<typeof useConversasEPastas>;
  /** Fecha tudo e volta para a Consulta. */
  onIrParaConsulta: () => void;
  /** Cabeçalho do recipiente, quando não há pasta aberta nem seleção. */
  topo: ReactNode;
  rodape?: ReactNode;
  /** Botão flutuante de nova consulta (tela cheia; a gaveta tem o seu no topo). */
  comBotaoFlutuante?: boolean;
}

export function PainelNavegacao({ aba, chat, dados, onIrParaConsulta, topo, rodape, comBotaoFlutuante }: Props) {
  const selecao = useCamada<Set<string>>();
  const pastaAberta = useCamada<string>();
  const folha = useCamada<Folha>();

  const nomesDasPastas = useMemo(() => new Map(dados.folders.map(p => [p.id, p.name])), [dados.folders]);
  const grupos = useMemo(() => agruparConversas(dados.conversations), [dados.conversations]);
  const pasta = pastaAberta.valor ? dados.folders.find(p => p.id === pastaAberta.valor) : undefined;
  const selecionadas = selecao.valor;

  function abrirConversa(id: string) {
    void chat.handleSelectConversation(id);
    onIrParaConsulta();
  }

  function alternar(id: string) {
    const proxima = new Set(selecionadas ?? []);
    if (proxima.has(id)) proxima.delete(id); else proxima.add(id);
    selecao.abrir(proxima);
  }

  const item = (c: ConversationSummary, mostrarPasta: boolean) => (
    <ItemConversa
      key={c.id}
      conversa={c}
      nomeDaPasta={mostrarPasta && c.folder_id ? nomesDasPastas.get(c.folder_id) : undefined}
      ativa={c.id === chat.activeConvId}
      selecionando={selecionadas !== null}
      selecionada={selecionadas?.has(c.id) ?? false}
      onAbrir={abrirConversa}
      onAcoes={conversa => folha.abrir({ tipo: 'acoes', conversa })}
      onAlternar={alternar}
    />
  );

  // ── Topo ──────────────────────────────────────────────────────────────
  let cabecalho: ReactNode = topo;
  if (selecionadas) {
    cabecalho = (
      <header className="mv-hdr mv-hdr-sel">
        <div className="mv-hdr-t"><b>{selecionadas.size === 1 ? '1 selecionada' : `${selecionadas.size} selecionadas`}</b></div>
        <button type="button" className="mv-btn-texto" onClick={() => selecao.fechar()}>Cancelar</button>
      </header>
    );
  } else if (pasta) {
    const n = dados.convsByFolder[pasta.id]?.length ?? 0;
    cabecalho = (
      <header className="mv-hdr">
        <button type="button" className="mv-ib" aria-label="Voltar" onClick={() => pastaAberta.fechar()}><Icone n="chevL" /></button>
        <div className="mv-hdr-t"><b>{pasta.name}</b><span>{n === 1 ? '1 conversa' : `${n} conversas`}</span></div>
        <button type="button" className="mv-ib" aria-label="Editar pasta" onClick={() => folha.abrir({ tipo: 'pasta', pasta })}>
          <Icone n="edit" />
        </button>
      </header>
    );
  }

  // ── Corpo ─────────────────────────────────────────────────────────────
  let corpo: ReactNode;
  if (pasta) {
    const conversas = dados.convsByFolder[pasta.id] ?? [];
    corpo = (
      <>
        {pasta.clinical_context && (
          <div className="mv-nota mv-pad-lados mv-nota-pasta">
            <Icone n="info" s={16} />
            <span><b>Contexto para a IA:</b> {pasta.clinical_context}</span>
          </div>
        )}
        <div className="mv-pad-lados mv-pad-baixo">
          <button type="button" className="mv-btn mv-btn-go mv-full" onClick={() => { chat.handleNew(pasta.id, pasta.name); onIrParaConsulta(); }}>
            <Icone n="plus" w={2.2} />Nova consulta nesta pasta
          </button>
        </div>
        {conversas.length === 0
          ? <Vazio icone="folder" titulo="Pasta vazia" texto="Comece uma consulta aqui para usar o contexto desta pasta." />
          : conversas.map(c => item(c, false))}
      </>
    );
  } else if (aba === 'historico') {
    corpo = dados.carregandoConversas ? <Esqueleto /> : grupos.length === 0 ? (
      <Vazio icone="clock" titulo="Nenhuma consulta ainda" texto="Suas conversas ficam salvas aqui, agrupadas por data." />
    ) : grupos.map(g => (
      <section key={g.rotulo} aria-label={g.rotulo}>
        <h3 className="mv-gh">{g.rotulo}</h3>
        {g.itens.map(c => item(c, true))}
      </section>
    ));
  } else {
    corpo = (
      <>
        {/* No TOPO, e não depois da lista: com muitas pastas o botão ficava lá
            embaixo, fora da tela, e criar pasta exigia rolar tudo. */}
        <div className="mv-pad-lados mv-pad-cima mv-pad-baixo">
          <button type="button" className="mv-btn mv-btn-sec mv-full" onClick={() => folha.abrir({ tipo: 'pasta' })}>
            <Icone n="plus" s={20} />Nova pasta
          </button>
        </div>
        {dados.folders.length === 0 && (
          <Vazio icone="folder" titulo="Nenhuma pasta" texto="Pastas guardam conversas de um paciente ou de um tema, com um contexto que a IA usa em todas elas." />
        )}
        {dados.folders.map(p => {
          const n = dados.convsByFolder[p.id]?.length ?? 0;
          return (
            <button key={p.id} type="button" className="mv-li mv-li-pasta-linha" onClick={() => pastaAberta.abrir(p.id)}>
              <span className="mv-fi"><Icone n="folder" /></span>
              <span className="mv-li-t"><b>{p.name}</b><span className="mv-li-m">{p.clinical_context || 'Sem contexto'}</span></span>
              <span className="mv-cnt" aria-label={`${n} conversas`}>{n}</span>
              <Icone n="chevR" s={20} />
            </button>
          );
        })}
      </>
    );
  }

  // ── Folhas ────────────────────────────────────────────────────────────
  const f = folha.valor;
  let folhaAberta: ReactNode = null;
  if (f?.tipo === 'acoes') {
    folhaAberta = (
      <SheetAcoes
        titulo={tituloDe(f.conversa)}
        onFechar={() => folha.fechar()}
        onRenomear={() => folha.abrir({ tipo: 'renomear', conversa: f.conversa })}
        onMover={() => folha.abrir({ tipo: 'mover', ids: [f.conversa.id], pastaAtual: f.conversa.folder_id })}
        onSelecionar={() => folha.fechar(() => selecao.abrir(new Set([f.conversa.id])))}
      />
    );
  } else if (f?.tipo === 'renomear') {
    folhaAberta = (
      <SheetRenomear
        tituloAtual={f.conversa.title}
        onFechar={() => folha.fechar()}
        onSalvar={titulo => {
          dados.handleRenameConversation(f.conversa.id, titulo);
          folha.fechar();
        }}
      />
    );
  } else if (f?.tipo === 'mover') {
    folhaAberta = (
      <SheetMover
        quantas={f.ids.length}
        pastas={dados.folders}
        pastaAtual={f.pastaAtual}
        onFechar={() => folha.fechar()}
        onMover={destino => {
          if (f.ids.length === 1) dados.handleMoveConv(f.ids[0], destino);
          else dados.moverVarias({ ids: f.ids, folderId: destino });
          // Movidas: sai também do modo seleção, se era dele que vinham.
          folha.fechar(selecionadas ? () => selecao.fechar() : undefined);
        }}
      />
    );
  } else if (f?.tipo === 'pasta') {
    const editando = f.pasta;
    folhaAberta = (
      <SheetPasta
        pasta={editando}
        onFechar={() => folha.fechar()}
        onSalvar={(name, clinicalContext, folderKind) => {
          if (editando) dados.atualizarPasta({ id: editando.id, name, clinicalContext, folderKind });
          // Criar abre uma consulta nova dentro da pasta (ver `useConversasEPastas`).
          else dados.criarPasta({ name, clinicalContext, folderKind });
          folha.fechar();
        }}
        onExcluir={editando ? () => {
          dados.handleDeleteFolder(editando.id);
          folha.fechar(() => pastaAberta.fechar());
        } : undefined}
      />
    );
  }

  return (
    <div className="mv-painel">
      {cabecalho}
      {chat.streaming && (
        <button type="button" className="mv-pilula" onClick={onIrParaConsulta}>
          <span className="mv-spin mv-spin-claro" aria-hidden="true" />
          <b>Respondendo: {chat.topbarTitle}</b>
          <em>Ver</em>
        </button>
      )}
      <div className="mv-painel-corpo rolagem">
        {corpo}
        {comBotaoFlutuante && !selecionadas && !pasta && aba === 'historico' && (
          <button type="button" className="mv-btn mv-btn-go mv-fab" onClick={() => { chat.handleNew(); onIrParaConsulta(); }}>
            <Icone n="plus" w={2.2} />Nova consulta
          </button>
        )}
      </div>
      {selecionadas ? (
        <div className="mv-selbar">
          <button
            type="button"
            className="mv-btn mv-btn-pri mv-full"
            disabled={selecionadas.size === 0}
            onClick={() => folha.abrir({ tipo: 'mover', ids: [...selecionadas] })}
          >
            <Icone n="move" s={20} />
            {selecionadas.size === 0 ? 'Toque nas conversas' : `Mover ${selecionadas.size} para…`}
          </button>
        </div>
      ) : rodape}
      {folhaAberta}
    </div>
  );
}

function Vazio({ icone, titulo, texto }: { icone: 'clock' | 'folder'; titulo: string; texto: string }) {
  return (
    <div className="mv-vazio">
      <div className="mv-vazio-i"><Icone n={icone} s={28} /></div>
      <b>{titulo}</b>
      <p>{texto}</p>
    </div>
  );
}

function Esqueleto() {
  return (
    <div aria-busy="true" aria-label="Carregando conversas">
      {[72, 58, 80, 64, 50, 70].map((w, i) => (
        <div key={i} className="mv-sk-linha">
          <div className="mv-sk" style={{ width: `${w}%`, height: 16 }} />
          <div className="mv-sk" style={{ width: '28%', height: 12 }} />
        </div>
      ))}
    </div>
  );
}
