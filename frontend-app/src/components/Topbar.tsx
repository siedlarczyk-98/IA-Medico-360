import { useEffect, useRef, useState } from 'react';

import { MAX_TITULO_CONVERSA } from '../api/conversations';
import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  title: string;
  onMenuToggle: () => void;
  /**
   * Renomeia a conversa aberta. Sem ele (tela de nova consulta), o lápis some:
   * não há o que renomear. Antes o lápis estava sempre lá e era só desenho —
   * clicar nele não fazia nada (homologação, 2026-09-25).
   */
  onRenomear?: (titulo: string) => void;
}

/**
 * O seletor de modos (Orquestrador / Agregador) foi removido junto com a
 * retirada do Agregador da interface: com um modo só, o switcher era um botão
 * que não levava a lugar nenhum. Ver git para o que havia aqui.
 */
export function Topbar({ title, onMenuToggle, onRenomear }: Props) {
  const isMobile = useIsMobile();
  // Mesmo gesto da lista (`ConvItem`): Enter ou sair do campo salva, Esc desiste.
  const [editando, setEditando] = useState(false);
  const [rascunho, setRascunho] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editando) inputRef.current?.select();
  }, [editando]);

  function comecar() {
    setRascunho(title);
    setEditando(true);
  }

  function salvar() {
    if (!editando) return;
    const novo = rascunho.replace(/\s+/g, ' ').trim();
    if (novo && novo !== title) onRenomear?.(novo);
    setEditando(false);
  }

  return (
    <header style={{
      height: 54, borderBottom: '1px solid var(--line2)',
      display: 'flex', alignItems: 'center', padding: '0 16px', gap: 10,
      flexShrink: 0,
    }}>
      {isMobile && (
        // A única porta para a gaveta no celular: era 34px e sem nome
        // acessível — o leitor de tela anunciava só "botão".
        <button
          onClick={onMenuToggle}
          aria-label="Abrir menu"
          style={{
            width: 'var(--toque-min)', height: 'var(--toque-min)', borderRadius: 8, border: '1px solid var(--line2)',
            background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--pen)', flexShrink: 0, cursor: 'pointer',
          }}
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <path d="M2 4 H14 M2 8 H14 M2 12 H14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      )}

      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
        {editando ? (
          <input
            ref={inputRef}
            value={rascunho}
            maxLength={MAX_TITULO_CONVERSA}
            aria-label="Novo título da conversa"
            onChange={e => setRascunho(e.target.value)}
            onBlur={salvar}
            onKeyDown={e => {
              if (e.key === 'Enter') salvar();
              if (e.key === 'Escape') setEditando(false);
            }}
            style={{ flex: 1, maxWidth: 480, minWidth: 0, fontSize: 'var(--texto-campo)', fontWeight: 600, color: 'var(--ink)', background: '#fff', border: 'none', outline: '1px solid var(--green)', borderRadius: 4, padding: '4px 6px' }}
          />
        ) : (
          <>
            <span style={{ fontSize: 'var(--texto-apoio)', fontWeight: 600, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {title}
            </span>
            {onRenomear && (
              <button
                type="button"
                onClick={comecar}
                aria-label="Renomear conversa"
                title="Renomear conversa"
                className="topbar-renomear"
                style={{
                  width: 'var(--toque-min)', height: 'var(--toque-min)', flexShrink: 0, border: 'none', borderRadius: 6,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
                }}
              >
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M11 3 L4 10 L3 13 L6 12 L13 5 Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" fill="none" />
                </svg>
              </button>
            )}
          </>
        )}
      </div>
    </header>
  );
}
