import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { completeOnboarding } from '../api/auth';
import { isAuthenticated, setToken } from '../lib/auth';

const BRAZIL_STATES = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA',
  'MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN',
  'RS','RO','RR','SC','SP','SE','TO',
];

const MED_STATUS_OPTIONS = [
  { value: 'graduando', label: 'Aluno de graduação' },
  { value: 'generalista', label: 'Médico generalista' },
  { value: 'residente', label: 'Médico residente' },
  { value: 'especialista', label: 'Médico especialista' },
];

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  border: '1px solid var(--line)',
  borderRadius: 8,
  fontSize: 14,
  color: 'var(--ink)',
  outline: 'none',
  background: '#fff',
  boxSizing: 'border-box',
  transition: 'border-color 0.15s',
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--pen)',
  letterSpacing: '0.03em',
  display: 'block',
  marginBottom: 6,
};

export function OnboardingPage() {
  const navigate = useNavigate();

  if (!isAuthenticated()) {
    navigate('/login', { replace: true });
    return null;
  }

  const [form, setForm] = useState({
    name: '',
    med_status: '',
    crm: '',
    crm_state: '',
    enrollment_date: '',
    phone_number: '',
  });
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const isGraduando = form.med_status === 'graduando';
  const isMedico = ['generalista', 'residente', 'especialista'].includes(form.med_status);

  function update(field: string, value: string) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  function focusBorder(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) {
    e.target.style.borderColor = 'var(--petrol)';
  }
  function blurBorder(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) {
    e.target.style.borderColor = 'var(--line)';
  }

  const canSubmit =
    form.name.trim() &&
    form.med_status &&
    form.phone_number.trim() &&
    termsAccepted &&
    (isGraduando ? !!form.enrollment_date : isMedico ? (!!form.crm && !!form.crm_state) : false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError('');
    setLoading(true);
    try {
      const res = await completeOnboarding({
        name: form.name.trim(),
        phone_number: form.phone_number.replace(/\D/g, ''),
        med_status: form.med_status,
        crm: isMedico ? form.crm : undefined,
        crm_state: isMedico ? form.crm_state : undefined,
        enrollment_date: isGraduando ? form.enrollment_date : undefined,
      });
      setToken(res.access_token);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar dados');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--fill2)',
      padding: 24,
    }}>
      <div style={{
        width: '100%',
        maxWidth: 440,
        background: '#fff',
        border: '1px solid var(--line)',
        borderRadius: 16,
        padding: '40px 36px',
        boxShadow: '0 4px 24px rgba(14,37,45,0.07)',
      }}>
        <div style={{ marginBottom: 28 }}>
          <div style={{
            display: 'inline-block',
            background: 'var(--mint)',
            color: 'var(--petrol)',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.06em',
            padding: '3px 10px',
            borderRadius: 20,
            marginBottom: 12,
          }}>
            ACESSO BETA
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)', marginBottom: 6 }}>
            Complete seu perfil
          </h1>
          <p style={{ fontSize: 13, color: 'var(--pen2)', lineHeight: 1.5 }}>
            Precisamos de algumas informações para liberar seu acesso completo.
          </p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Nome */}
          <div>
            <label style={labelStyle}>Nome completo</label>
            <input
              type="text"
              required
              autoFocus
              placeholder="Dr. João Silva"
              value={form.name}
              onChange={e => update('name', e.target.value)}
              style={inputStyle}
              onFocus={focusBorder}
              onBlur={blurBorder}
            />
          </div>

          {/* Você é */}
          <div>
            <label style={labelStyle}>Você é</label>
            <select
              required
              value={form.med_status}
              onChange={e => {
                update('med_status', e.target.value);
                update('crm', '');
                update('crm_state', '');
                update('enrollment_date', '');
              }}
              style={{ ...inputStyle, cursor: 'pointer' }}
              onFocus={focusBorder}
              onBlur={blurBorder}
            >
              <option value="" disabled>Selecione…</option>
              {MED_STATUS_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Condicional — Graduando */}
          {isGraduando && (
            <div style={{ animation: 'fadeIn 0.2s ease' }}>
              <label style={labelStyle}>Data de ingresso na faculdade</label>
              <input
                type="date"
                required
                value={form.enrollment_date}
                onChange={e => update('enrollment_date', e.target.value)}
                style={inputStyle}
                onFocus={focusBorder}
                onBlur={blurBorder}
              />
            </div>
          )}

          {/* Condicional — Médico formado */}
          {isMedico && (
            <div style={{ display: 'flex', gap: 12, animation: 'fadeIn 0.2s ease' }}>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>CRM</label>
                <input
                  type="text"
                  required
                  inputMode="numeric"
                  placeholder="123456"
                  value={form.crm}
                  onChange={e => update('crm', e.target.value.replace(/\D/g, ''))}
                  style={inputStyle}
                  onFocus={focusBorder}
                  onBlur={blurBorder}
                />
              </div>
              <div style={{ width: 100 }}>
                <label style={labelStyle}>UF</label>
                <select
                  required
                  value={form.crm_state}
                  onChange={e => update('crm_state', e.target.value)}
                  style={{ ...inputStyle, cursor: 'pointer' }}
                  onFocus={focusBorder}
                  onBlur={blurBorder}
                >
                  <option value="" disabled>UF</option>
                  {BRAZIL_STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>
          )}

          {/* Telefone */}
          <div>
            <label style={labelStyle}>Telefone</label>
            <div style={{ display: 'flex' }}>
              <span style={{
                padding: '10px 10px',
                border: '1px solid var(--line)',
                borderRight: 'none',
                borderRadius: '8px 0 0 8px',
                fontSize: 14,
                color: 'var(--pen2)',
                background: 'var(--fill2)',
                whiteSpace: 'nowrap',
                lineHeight: '20px',
              }}>
                +55
              </span>
              <input
                type="tel"
                required
                inputMode="numeric"
                placeholder="11 99999-9999"
                value={form.phone_number}
                onChange={e => update('phone_number', e.target.value.replace(/\D/g, ''))}
                style={{ ...inputStyle, borderRadius: '0 8px 8px 0', flex: 1 }}
                onFocus={focusBorder}
                onBlur={blurBorder}
              />
            </div>
          </div>

          {/* Termos */}
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={termsAccepted}
              onChange={e => setTermsAccepted(e.target.checked)}
              style={{ marginTop: 2, accentColor: 'var(--petrol)', flexShrink: 0, width: 15, height: 15 }}
            />
            <span style={{ fontSize: 12.5, color: 'var(--pen2)', lineHeight: 1.5 }}>
              Li e aceito os{' '}
              <a
                href="#"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--petrol)', textDecoration: 'underline' }}
              >
                Termos de Uso
              </a>
              {' '}e a{' '}
              <a
                href="#"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--petrol)', textDecoration: 'underline' }}
              >
                Política de Privacidade
              </a>
            </span>
          </label>

          {error && (
            <p style={{ fontSize: 12, color: 'var(--red)', background: 'var(--red-bg)', padding: '8px 10px', borderRadius: 6 }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !canSubmit}
            style={{
              padding: '12px 16px',
              background: loading || !canSubmit ? 'var(--fill)' : 'var(--petrol)',
              color: loading || !canSubmit ? 'var(--pen3)' : '#fff',
              border: 'none',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: loading || !canSubmit ? 'not-allowed' : 'pointer',
              transition: 'background 0.15s',
              marginTop: 4,
            }}
          >
            {loading ? 'Salvando…' : 'Começar a usar →'}
          </button>
        </form>
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
