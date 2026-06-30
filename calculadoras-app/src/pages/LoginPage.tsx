import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { requestOTP, verifyOTP } from '../api/auth';
import { setToken } from '../lib/auth';

export function LoginPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<'email' | 'otp'>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleEmailSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await requestOTP(email);
      setStep('otp');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao enviar código');
    } finally {
      setLoading(false);
    }
  }

  async function handleOTPSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await verifyOTP(email, code);
      setToken(res.access_token);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Código inválido');
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
        maxWidth: 400,
        background: '#fff',
        border: '1px solid var(--line)',
        borderRadius: 16,
        padding: '40px 36px',
        boxShadow: '0 4px 24px rgba(14,37,45,0.07)',
      }}>
        <div style={{ marginBottom: 32, textAlign: 'center' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 44,
            height: 44,
            borderRadius: 12,
            background: 'var(--mint)',
            marginBottom: 16,
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M9 12l2 2 4-4m-5-7H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V9l-5-5z" stroke="var(--petrol)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)', marginBottom: 4 }}>
            Calculadoras Clínicas
          </h1>
          <p style={{ fontSize: 13, color: 'var(--pen2)', lineHeight: 1.4 }}>
            {step === 'email'
              ? 'Entre com seu email para acessar'
              : <><span>Código enviado para</span><br /><strong style={{ color: 'var(--ink)' }}>{email}</strong></>
            }
          </p>
        </div>

        {step === 'email' ? (
          <form onSubmit={handleEmailSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--pen)', letterSpacing: '0.03em', display: 'block', marginBottom: 6 }}>
                Email
              </label>
              <input
                type="email"
                required
                autoFocus
                placeholder="seu@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: '1px solid var(--line)',
                  borderRadius: 8,
                  fontSize: 14,
                  color: 'var(--ink)',
                  outline: 'none',
                  transition: 'border-color 0.15s',
                  background: '#fff',
                  boxSizing: 'border-box',
                }}
                onFocus={e => (e.target.style.borderColor = 'var(--petrol)')}
                onBlur={e => (e.target.style.borderColor = 'var(--line)')}
              />
            </div>

            {error && (
              <p style={{ fontSize: 12, color: 'var(--red)', background: 'var(--red-bg)', padding: '8px 10px', borderRadius: 6 }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '11px 16px',
                background: loading ? 'var(--fill)' : 'var(--petrol)',
                color: loading ? 'var(--pen3)' : '#fff',
                border: 'none',
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s',
                marginTop: 4,
              }}
            >
              {loading ? 'Enviando…' : 'Enviar código'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleOTPSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--pen)', letterSpacing: '0.03em', display: 'block', marginBottom: 6 }}>
                Código de 6 dígitos
              </label>
              <input
                type="text"
                required
                autoFocus
                inputMode="numeric"
                maxLength={6}
                placeholder="000000"
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
                style={{
                  width: '100%',
                  padding: '12px 16px',
                  border: '1px solid var(--line)',
                  borderRadius: 8,
                  fontSize: 26,
                  fontWeight: 700,
                  letterSpacing: '0.25em',
                  textAlign: 'center',
                  color: 'var(--ink)',
                  outline: 'none',
                  transition: 'border-color 0.15s',
                  background: '#fff',
                  boxSizing: 'border-box',
                }}
                onFocus={e => (e.target.style.borderColor = 'var(--petrol)')}
                onBlur={e => (e.target.style.borderColor = 'var(--line)')}
              />
            </div>

            {error && (
              <p style={{ fontSize: 12, color: 'var(--red)', background: 'var(--red-bg)', padding: '8px 10px', borderRadius: 6 }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '11px 16px',
                background: loading ? 'var(--fill)' : 'var(--petrol)',
                color: loading ? 'var(--pen3)' : '#fff',
                border: 'none',
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s',
                marginTop: 4,
              }}
            >
              {loading ? 'Verificando…' : 'Entrar'}
            </button>

            <button
              type="button"
              onClick={() => { setStep('email'); setError(''); setCode(''); }}
              style={{
                padding: '8px',
                background: 'none',
                border: 'none',
                fontSize: 13,
                color: 'var(--pen3)',
                cursor: 'pointer',
                textAlign: 'center',
              }}
            >
              ← Usar outro email
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
