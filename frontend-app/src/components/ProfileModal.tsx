import { useEffect, useState } from 'react';
import { getMe, updateProfile, deleteAccount, listarEspecialidades, type Especialidade } from '../api/auth';
import { setToken, logout } from '../lib/auth';
import { useIsMobile } from '../hooks/useIsMobile';

// De onde veio a especialidade, em português, para explicar por que o campo
// está travado. Sem esta frase o médico vê um texto cinza e não sabe se é bug.
const ORIGEM_LEGIVEL: Record<string, string> = {
  cadastro: 'Veio do seu cadastro.',
  waid_grupo: 'Veio do seu cadastro.',
  cfm: 'Verificada no Conselho Federal de Medicina.',
  admin: 'Ajustada pelo suporte.',
};

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

export function ProfileModal({ onClose, onSuccess }: Props) {
  const isMobile = useIsMobile();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [crmLabel, setCrmLabel] = useState('');
  const [especialidade, setEspecialidade] = useState('');
  // O rótulo vem pronto do servidor; sem ele, o campo travado mostraria o slug
  // ("ortopedia-e-traumatologia") porque a lista só é buscada quando editável.
  const [especialidadeNome, setEspecialidadeNome] = useState('');
  const [origemEspecialidade, setOrigemEspecialidade] = useState<string | null>(null);
  const [especialidadeEditavel, setEspecialidadeEditavel] = useState(false);
  const [especialidades, setEspecialidades] = useState<Especialidade[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmName, setConfirmName] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [showDeleteZone, setShowDeleteZone] = useState(false);

  useEffect(() => {
    getMe()
      .then(user => {
        setName(user.name ?? '');
        setEmail(user.email);
        setCrmLabel(user.crm && user.crm_state ? `CRM/${user.crm_state} ${user.crm}` : '');
        setEspecialidade(user.specialty_slug ?? '');
        setEspecialidadeNome(user.specialty ?? '');
        setOrigemEspecialidade(user.specialty_source ?? null);
        // O servidor decide se o campo é editável — a regra mora em
        // `identidade.usuario_pode_editar`, não aqui. A tela só obedece.
        const editavel = user.specialty_editavel ?? true;
        setEspecialidadeEditavel(editavel);
        if (editavel) {
          listarEspecialidades().then(setEspecialidades).catch(() => setEspecialidades([]));
        }
      })
      .catch(() => setError('Não foi possível carregar os dados do perfil.'))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await updateProfile({
        name: name.trim(),
        email: email.trim(),
        ...(especialidadeEditavel && especialidade ? { specialty_slug: especialidade } : {}),
      });
      setToken(res.access_token);
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao salvar');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await deleteAccount(confirmName);
      logout();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao excluir conta');
      setDeleting(false);
    }
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
          width: isMobile ? 'calc(100vw - 32px)' : 400,
          maxWidth: 400,
          background: 'var(--paper)', borderRadius: 14,
          boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid var(--line2)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>Editar perfil</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen3)', display: 'flex' }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div style={{ padding: '20px 24px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', color: 'var(--pen3)', fontSize: 13, padding: '16px 0' }}>Carregando…</div>
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
                <input
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  type="email"
                  style={inputStyle}
                  placeholder="seu@email.com"
                />
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
                    <p style={{ fontSize: 11, color: 'var(--pen3)', margin: '5px 0 0', lineHeight: 1.4 }}>
                      {ORIGEM_LEGIVEL[origemEspecialidade ?? ''] ?? 'Definida pelo seu cadastro.'}{' '}
                      Se estiver incorreta, fale com o suporte.
                    </p>
                  </>
                )}
              </Field>

              {error && <p style={{ fontSize: 12, color: '#ef4444', margin: '8px 0 0' }}>{error}</p>}
              <button
                onClick={handleSave}
                disabled={saving || !name.trim() || !email.trim()}
                style={{
                  width: '100%', marginTop: 16,
                  background: 'var(--ink)', color: '#fff',
                  border: 'none', borderRadius: 8, padding: '10px',
                  fontSize: 13, fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer',
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
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: '#ef4444', padding: 0 }}
            >
              Excluir minha conta
            </button>
          ) : (
            <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '14px' }}>
              <p style={{ fontSize: 12, color: '#991b1b', fontWeight: 600, margin: '0 0 4px' }}>Excluir conta permanentemente</p>
              <p style={{ fontSize: 11.5, color: '#b91c1c', margin: '0 0 12px', lineHeight: 1.4 }}>
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
                  style={{ flex: 1, background: '#fff', border: '1px solid var(--line2)', borderRadius: 6, padding: '8px', fontSize: 12, cursor: 'pointer', color: 'var(--pen)' }}
                >
                  Cancelar
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleting || !confirmName}
                  style={{ flex: 1, background: '#ef4444', color: '#fff', border: 'none', borderRadius: 6, padding: '8px', fontSize: 12, fontWeight: 600, cursor: deleting || !confirmName ? 'not-allowed' : 'pointer', opacity: deleting || !confirmName ? 0.6 : 1 }}
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
      <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--pen3)', marginBottom: 5, letterSpacing: 0.3 }}>
        {label.toUpperCase()}
      </label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box',
  border: '1px solid var(--line2)', borderRadius: 8,
  padding: '9px 11px', fontSize: 13, color: 'var(--ink)',
  background: '#fff', outline: 'none',
};
