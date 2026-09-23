import { useEffect, useRef } from 'react';
import { MAX_CHARS_EVOLUCAO, type Folder, type FolderKind } from '../api/folders';
import { useFormularioPasta } from '../hooks/useFormularioPasta';

interface Props {
  /** Pasta existente para editar; ausente = criando uma nova. */
  folder?: Folder;
  onClose: () => void;
  onSave: (name: string, clinicalContext: string, folderKind: FolderKind) => void;
  saving?: boolean;
}

/**
 * Criação e edição de pasta, com a evolução do paciente.
 *
 * Por que um modal e não o input inline da sidebar: a evolução é um texto de
 * várias linhas, e o campo inline mal cabe um nome. O mesmo modal serve para
 * criar e para editar depois — o médico não precisa aprender duas telas.
 *
 * O campo é OPCIONAL e a tela deixa isso explícito. Uma pasta pode ser só
 * organização por tema ("Cardiologia", "Artigos para ler"), e um campo que
 * pareça obrigatório faria o médico inventar conteúdo para preenchê-lo.
 */
export function FolderModal({ folder, onClose, onSave, saving = false }: Props) {
  // Estado e validação vêm do hook compartilhado com a sheet da casca mobile.
  const {
    editando, name, setName, clinicalContext, setClinicalContext,
    folderKind, setFolderKind, textos, excedeu, podeSalvar, salvar: handleSave,
  } = useFormularioPasta(folder, onSave, saving);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  // Esc fecha. Sem isso o único jeito de sair é o X, que numa tela de texto
  // longo fica fora do campo de visão enquanto se escreve.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={editando ? 'Editar pasta' : 'Nova pasta'}
      style={{
        position: 'fixed', inset: 0, zIndex: 400,
        background: 'rgba(0,0,0,0.35)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          // Largura por `min()`, e altura limitada à tela VISÍVEL (`dvh`) com
          // rolagem própria. Antes o cartão tinha `overflow: hidden` sem altura
          // máxima: com o teclado do celular aberto, o que passava da metade
          // da tela era cortado e não havia como rolar até lá.
          width: 'min(480px, calc(100vw - 32px))',
          maxHeight: 'calc(100dvh - 32px)',
          overflowY: 'auto',
          overscrollBehavior: 'contain',
          background: 'var(--paper)', borderRadius: 14,
          boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
        }}
      >
        <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid var(--line2)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>
            {editando ? 'Editar pasta' : 'Nova pasta'}
          </span>
          <button onClick={onClose} aria-label="Fechar" className="toque" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', padding: 0, margin: 'calc((var(--toque-min) - 16px) / -2)' }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div style={{ padding: '20px 24px' }}>
          {/* A pergunta vem PRIMEIRO porque decide o resto da tela: o rótulo do
              campo de contexto, o placeholder e o texto de ajuda. Perguntar
              depois faria o médico ler "Evolução do paciente" numa pasta de
              estudos antes de poder dizer que não é clínica. */}
          <div style={{ marginBottom: 16 }}>
            <span style={labelStyle}>Esta pasta é sobre um paciente?</span>
            <div role="radiogroup" aria-label="Tipo da pasta" style={{ display: 'flex', gap: 8 }}>
              {([
                { kind: 'clinical' as const, titulo: 'Sim, é clínica', sub: 'Acompanhamento de um paciente' },
                { kind: 'general' as const, titulo: 'Não', sub: 'Estudo, gestão ou tema' },
              ]).map(opt => {
                const ativo = folderKind === opt.kind;
                return (
                  <button
                    key={opt.kind}
                    role="radio"
                    aria-checked={ativo}
                    onClick={() => setFolderKind(opt.kind)}
                    style={{
                      flex: 1, textAlign: 'left', cursor: 'pointer',
                      border: `1px solid ${ativo ? 'var(--ink)' : 'var(--line2)'}`,
                      background: ativo ? 'var(--fill)' : '#fff',
                      borderRadius: 8, padding: '8px 10px',
                    }}
                  >
                    <span style={{ display: 'block', fontSize: 'var(--texto-apoio)', fontWeight: 600, color: 'var(--ink)' }}>
                      {opt.titulo}
                    </span>
                    <span style={{ display: 'block', fontSize: 'var(--texto-micro)', color: 'var(--pen3)', marginTop: 1 }}>
                      {opt.sub}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <label style={{ display: 'block', marginBottom: 16 }}>
            <span style={labelStyle}>Nome da pasta</span>
            <input
              ref={nameRef}
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSave(); }}
              style={inputStyle}
              placeholder="Ex.: Paciente Jorge, ou Cardiologia"
            />
          </label>

          <label style={{ display: 'block' }}>
            <span style={labelStyle}>
              {textos.rotulo} <span style={{ fontWeight: 400, color: 'var(--pen3)' }}>(opcional)</span>
            </span>
            <textarea
              value={clinicalContext}
              onChange={e => setClinicalContext(e.target.value)}
              rows={7}
              style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5, fontFamily: 'inherit' }}
              placeholder={textos.placeholder}
            />
          </label>

          {/* Explicar o efeito, não o campo. O médico decide o que escrever se
              souber que isto vai junto de TODA pergunta feita na pasta. */}
          <p style={{ fontSize: 'var(--texto-micro)', color: 'var(--pen3)', margin: '6px 0 0', lineHeight: 1.45 }}>
            {textos.ajuda}
          </p>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
            <span style={{ fontSize: 'var(--texto-micro)', color: excedeu ? '#ef4444' : 'var(--pen3)' }}>
              {clinicalContext.length.toLocaleString('pt-BR')} / {MAX_CHARS_EVOLUCAO.toLocaleString('pt-BR')}
            </span>
          </div>

          {excedeu && (
            <p style={{ fontSize: 'var(--texto-apoio)', color: '#ef4444', margin: '8px 0 0' }}>
              A evolução ficou acima do limite. Resuma o essencial do caso.
            </p>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button
              onClick={onClose}
              style={{ flex: 1, background: '#fff', border: '1px solid var(--line2)', borderRadius: 8, padding: '0 10px', minHeight: 'var(--toque-min)', fontSize: 'var(--texto-apoio)', cursor: 'pointer', color: 'var(--pen)' }}
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={!podeSalvar}
              style={{
                flex: 1,
                background: 'var(--ink)', color: '#fff',
                border: 'none', borderRadius: 8, padding: '10px',
                fontSize: 'var(--texto-apoio)', fontWeight: 600,
                cursor: podeSalvar ? 'pointer' : 'not-allowed',
                opacity: podeSalvar ? 1 : 0.6,
              }}
            >
              {saving ? 'Salvando…' : editando ? 'Salvar' : 'Criar pasta'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 'var(--texto-apoio)',
  fontWeight: 600,
  color: 'var(--pen)',
  marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  border: '1px solid var(--line2)',
  borderRadius: 8,
  padding: '11px 12px',
  fontSize: 'var(--texto-campo)',
  color: 'var(--ink)',
  background: '#fff',
  outline: 'none',
};
