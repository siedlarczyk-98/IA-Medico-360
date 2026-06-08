import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { registerBeta } from '../api/auth';

export function RegisterPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await registerBeta(email);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao solicitar acesso');
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
        {done ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{
              width: 48,
              height: 48,
              borderRadius: '50%',
              background: 'var(--mint)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 20px',
            }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                <path d="M9 12l2 2 4-4" stroke="var(--petrol)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="12" cy="12" r="10" stroke="var(--petrol)" strokeWidth="2" />
              </svg>
            </div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)', marginBottom: 8 }}>
              Verifique seu email
            </h2>
            <p style={{ fontSize: 13, color: 'var(--pen2)', lineHeight: 1.6, marginBottom: 24 }}>
              Enviamos um link de acesso para <strong style={{ color: 'var(--ink)' }}>{email}</strong>.
              <br />Clique no link para criar sua conta.
            </p>
            <button
              onClick={() => navigate('/login')}
              style={{
                fontSize: 13, color: 'var(--petrol)', background: 'none',
                border: '1px solid var(--line)', borderRadius: 8,
                padding: '8px 20px', cursor: 'pointer',
              }}
            >
              Já tenho conta — entrar
            </button>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: 32, textAlign: 'center' }}>
              <div style={{
                display: 'inline-block',
                background: 'var(--mint)',
                color: 'var(--petrol)',
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: '0.06em',
                padding: '3px 10px',
                borderRadius: 20,
                marginBottom: 14,
              }}>
                ACESSO BETA
              </div>
              <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)', marginBottom: 6 }}>
                Médico 360
              </h1>
              <p style={{ fontSize: 13, color: 'var(--pen2)', lineHeight: 1.5 }}>
                IA clínica para médicos.<br />
                Cadastre seu email e receba o link de acesso.
              </p>
            </div>

            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={{
                  fontSize: 12, fontWeight: 600, color: 'var(--pen)',
                  letterSpacing: '0.03em', display: 'block', marginBottom: 6,
                }}>
                  Email profissional
                </label>
                <input
                  type="email"
                  required
                  autoFocus
                  placeholder="seu@email.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 12px',
                    border: '1px solid var(--line)', borderRadius: 8,
                    fontSize: 14, color: 'var(--ink)', outline: 'none',
                    background: '#fff', boxSizing: 'border-box',
                    transition: 'border-color 0.15s',
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
                  border: 'none', borderRadius: 8,
                  fontSize: 14, fontWeight: 600,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  transition: 'background 0.15s',
                  marginTop: 4,
                }}
              >
                {loading ? 'Enviando…' : 'Solicitar acesso'}
              </button>

              <button
                type="button"
                onClick={() => navigate('/login')}
                style={{
                  padding: '8px', background: 'none', border: 'none',
                  fontSize: 13, color: 'var(--pen3)', cursor: 'pointer', textAlign: 'center',
                }}
              >
                Já tenho conta — entrar
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
