import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { embedToken } from '../api/auth';
import { setToken } from '../lib/auth';

export function EmbedAuthPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [erroDaChamada, setErroDaChamada] = useState('');

  // Parametro ausente e estado DERIVADO da URL: da para calcular no render.
  // Antes era `setError` dentro do efeito, o que dispara um render em
  // cascata so para mostrar uma mensagem que ja se sabia de antemao.
  const email = searchParams.get('email');
  const error = erroDaChamada || (!email ? 'Email não informado.' : '');

  useEffect(() => {
    if (!email) return;
    embedToken(email)
      .then(res => {
        setToken(res.access_token);
        navigate(res.onboarding_complete ? '/' : '/onboarding', { replace: true });
      })
      .catch(err => {
        setErroDaChamada(err instanceof Error ? err.message : 'Erro ao autenticar.');
      });
  }, [email]);

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--fill2)',
    }}>
      {error ? (
        <div style={{
          maxWidth: 360,
          textAlign: 'center',
          padding: 32,
          background: '#fff',
          border: '1px solid var(--line)',
          borderRadius: 16,
          boxShadow: '0 4px 24px rgba(14,37,45,0.07)',
        }}>
          <p style={{ fontSize: 14, color: 'var(--red)', marginBottom: 16 }}>{error}</p>
          <button
            onClick={() => navigate('/login')}
            style={{
              fontSize: 13, color: 'var(--petrol)', background: 'none',
              border: '1px solid var(--line)', borderRadius: 8,
              padding: '8px 16px', cursor: 'pointer',
            }}
          >
            Ir para o login
          </button>
        </div>
      ) : (
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: 36, height: 36, borderRadius: '50%',
            border: '3px solid var(--mint)', borderTopColor: 'var(--green)',
            animation: 'spin 0.8s linear infinite',
            margin: '0 auto 16px',
          }} />
          <p style={{ fontSize: 13, color: 'var(--pen2)' }}>Autenticando…</p>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}
    </div>
  );
}
