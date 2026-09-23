import { useState } from 'react';
import { ORIGEM_LEGIVEL, usePerfil } from '../hooks/usePerfil';

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

export function ProfileModal({ onClose, onSuccess }: Props) {
  // Carregar, salvar e excluir vêm do hook compartilhado com a casca mobile.
  const {
    name, setName, email, crmLabel, especialidade, setEspecialidade, especialidadeNome,
    origemEspecialidade, especialidadeEditavel, especialidades,
    loading, saving, error, deleting, salvar: handleSave, excluirConta,
  } = usePerfil({ onSuccess, onClose });
  const [confirmName, setConfirmName] = useState('');
  const [showDeleteZone, setShowDeleteZone] = useState(false);

  function handleDelete() {
    void excluirConta(confirmName);
  }

  return (
    <div
      onClick={onClose}
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
          width: 'min(400px, calc(100vw - 32px))',
          maxHeight: 'calc(100dvh - 32px)',
          overflowY: 'auto',
          overscrollBehavior: 'contain',
          background: 'var(--paper)', borderRadius: 14,
          boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
        }}
      >
        <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid var(--line2)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>Editar perfil</span>
          <button onClick={onClose} aria-label="Fechar" className="toque" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', padding: 0, margin: 'calc((var(--toque-min) - 16px) / -2)' }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div style={{ padding: '20px 24px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', color: 'var(--pen3)', fontSize: 'var(--texto-apoio)', padding: '16px 0' }}>Carregando…</div>
          ) : (
            <>
              <Field label="Nome completo">
                <input
                  value={name}
                  onChange={e => setName(e.target.value)}
                  style={inputStyle}
                  placeholder="Seu nome"
                />
              </Field>
              <Field label="Email">
                {/* Somente leitura (2026-09-21). A troca não pedia prova de posse
                    do endereço novo: dava para pôr o e-mail de um colega, e ele
                    caía nesta conta ao entrar pela área de membros. Para quem
                    entra por lá o e-mail já vem sincronizado; para quem entra por
                    código, ele é o login. Trocar é caminho de suporte. */}
                <div
                  data-testid="perfil-email"
                  style={{ ...inputStyle, background: 'var(--fill)', color: 'var(--pen)' }}
                >
                  {email}
                </div>
              </Field>
              {crmLabel && (
                <Field label="Registro">
                  {/* Somente leitura: trocar de CRM invalida a verificação e é
                      caminho de suporte, não de auto-serviço. */}
                  <div style={{ ...inputStyle, background: 'var(--fill)', color: 'var(--pen)' }}>
                    {crmLabel}
                  </div>
                </Field>
              )}

              <Field label="Especialidade">
                {especialidadeEditavel ? (
                  <select
                    value={especialidade}
                    onChange={e => setEspecialidade(e.target.value)}
                    style={inputStyle}
                  >
                    <option value="">Não informada</option>
                    {especialidades.map(esp => (
                      <option key={esp.slug} value={esp.slug}>{esp.nome}</option>
                    ))}
                  </select>
                ) : (
                  <>
                    <div style={{ ...inputStyle, background: 'var(--fill)', color: 'var(--pen)' }}>
                      {especialidadeNome || '—'}
                    </div>
                    {/* Explicar POR QUE está travado. Campo cinza sem motivo
                        parece defeito; com motivo, parece o que é. */}
                    <p style={{ fontSize: 'var(--texto-micro)', color: 'var(--pen3)', margin: '5px 0 0', lineHeight: 1.4 }}>
                      {ORIGEM_LEGIVEL[origemEspecialidade ?? ''] ?? 'Definida pelo seu cadastro.'}{' '}
                      Se estiver incorreta, fale com o suporte.
                    </p>
                  </>
                )}
              </Field>

              {error && <p style={{ fontSize: 'var(--texto-apoio)', color: '#ef4444', margin: '8px 0 0' }}>{error}</p>}
              <button
                onClick={handleSave}
                disabled={saving || !name.trim()}
                style={{
                  width: '100%', marginTop: 16,
                  background: 'var(--ink)', color: '#fff',
                  border: 'none', borderRadius: 8, padding: '10px',
                  fontSize: 'var(--texto-apoio)', fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer',
                  opacity: saving ? 0.7 : 1,
                }}
              >
                {saving ? 'Salvando…' : 'Salvar alterações'}
              </button>
            </>
          )}
        </div>

        <div style={{ borderTop: '1px solid var(--line2)', padding: '16px 24px 20px' }}>
          {!showDeleteZone ? (
            <button
              onClick={() => setShowDeleteZone(true)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 'var(--texto-apoio)', color: '#ef4444', padding: 0, minHeight: 'var(--toque-min)' }}
            >
              Excluir minha conta
            </button>
          ) : (
            <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '14px' }}>
              <p style={{ fontSize: 'var(--texto-apoio)', color: '#991b1b', fontWeight: 600, margin: '0 0 4px' }}>Excluir conta permanentemente</p>
              <p style={{ fontSize: 'var(--texto-micro)', color: '#b91c1c', margin: '0 0 12px', lineHeight: 1.4 }}>
                Esta ação não pode ser desfeita. Todos os seus dados serão removidos conforme a LGPD.
                Digite seu nome completo para confirmar.
              </p>
              <input
                value={confirmName}
                onChange={e => setConfirmName(e.target.value)}
                placeholder="Digite seu nome completo"
                style={{ ...inputStyle, marginBottom: 10, borderColor: '#fca5a5' }}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => { setShowDeleteZone(false); setConfirmName(''); }}
                  style={{ flex: 1, background: '#fff', border: '1px solid var(--line2)', borderRadius: 6, padding: '0 8px', minHeight: 'var(--toque-min)', fontSize: 'var(--texto-apoio)', cursor: 'pointer', color: 'var(--pen)' }}
                >
                  Cancelar
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleting || !confirmName}
                  style={{ flex: 1, background: '#ef4444', color: '#fff', border: 'none', borderRadius: 6, padding: '0 8px', minHeight: 'var(--toque-min)', fontSize: 'var(--texto-apoio)', fontWeight: 600, cursor: deleting || !confirmName ? 'not-allowed' : 'pointer', opacity: deleting || !confirmName ? 0.6 : 1 }}
                >
                  {deleting ? 'Excluindo…' : 'Excluir conta'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: 'block', fontSize: 'var(--texto-micro)', fontWeight: 600, color: 'var(--pen3)', marginBottom: 5, letterSpacing: 0.3 }}>
        {label.toUpperCase()}
      </label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box',
  border: '1px solid var(--line2)', borderRadius: 8,
  padding: '11px 12px', fontSize: 'var(--texto-campo)', color: 'var(--ink)',
  background: '#fff', outline: 'none',
};
