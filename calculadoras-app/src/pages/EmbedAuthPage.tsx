/**
 * Entrada pelo embed do LMS.
 *
 * A identidade vem por handshake com a Waid (`shared/embed/identidade.ts`), não
 * mais pelo `?email=` da URL — que não provava nada: quem soubesse o e-mail de
 * um colega recebia a sessão dele.
 *
 * Diferença em relação ao `frontend-app`: aqui sempre navegamos para "/". O
 * onboarding deste app é tratado depois, dentro do `RequireAuth`, por um
 * `OnboardingGate` em modo "avisar" — bloquear uma calculadora de creatinina
 * porque falta cadastro seria hostil.
 */

import { Navigate, useNavigate } from 'react-router-dom';

import { useIdentidadeWaid } from '@shared/embed/identidade';

import { setToken } from '../lib/auth';

// Mesma convenção de `api/auth.ts`: vazio em dev (o proxy do Vite cuida do
// CORS), domínio do backend em produção.
const API_BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '';
const WAID_ORIGIN =
  import.meta.env.VITE_WAID_ORIGIN ?? 'https://www.medico360.app';

export function EmbedAuthPage() {
  const navigate = useNavigate();

  const { fase, erro } = useIdentidadeWaid({
    apiBase: API_BASE,
    waidOrigin: WAID_ORIGIN,
    aoAutenticar: resposta => {
      setToken(resposta.access_token);
      navigate('/', { replace: true });
    },
  });

  if (fase === 'pronto') return <Navigate to="/" replace />;

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--fill2)',
    }}>
      {fase === 'erro' ? (
        <div style={{
          maxWidth: 380,
          textAlign: 'center',
          padding: 32,
          background: '#fff',
          border: '1px solid var(--line)',
          borderRadius: 16,
          boxShadow: '0 4px 24px rgba(14,37,45,0.07)',
        }}>
          <p style={{ fontSize: 14, color: 'var(--ink)', margin: '0 0 8px', fontWeight: 600 }}>
            {erro?.mensagem}
          </p>
          <p style={{ fontSize: 13, color: 'var(--pen2)', margin: '0 0 20px', lineHeight: 1.5 }}>
            {erro?.tipo === 'sem_iframe'
              // Caso conhecido: os aplicativos da Waid abrem a seção sem iframe,
              // e ali a plataforma não tem como nos dizer quem é o médico.
              ? 'No aplicativo, entre pelo seu e-mail. Pelo navegador, o acesso é automático.'
              : 'Você pode entrar pelo seu e-mail enquanto isso.'}
          </p>
          <button
            onClick={() => navigate('/login')}
            style={{
              fontSize: 13, color: 'var(--petrol)', background: 'none',
              border: '1px solid var(--line)', borderRadius: 8,
              padding: '8px 16px', cursor: 'pointer',
            }}
          >
            Entrar por e-mail
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
          <p style={{ fontSize: 13, color: 'var(--pen2)' }}>
            {fase === 'trocando' ? 'Confirmando sua identidade…' : 'Autenticando…'}
          </p>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}
    </div>
  );
}
