/**
 * Entrada pelo embed do LMS.
 *
 * A identidade vem por handshake com a Waid (`shared/embed/identidade.ts`), não
 * mais pelo `?email=` da URL. O `?email=` não provava nada: quem soubesse o
 * e-mail de um colega recebia a sessão dele.
 *
 * SEM FALLBACK, DE PROPÓSITO. Se o handshake falhar, esta tela mostra erro e
 * oferece o login por e-mail (OTP) — que é porta legítima, não o caminho
 * inseguro. Um fallback silencioso para o `?email=` faria o piloto parecer um
 * sucesso mesmo quebrado, e é justamente o que precisamos conseguir enxergar.
 */

import { Navigate, useNavigate } from 'react-router-dom';

import { useIdentidadeWaid } from '@shared/embed/identidade';

import { setToken } from '../lib/auth';

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const WAID_ORIGIN =
  import.meta.env.VITE_WAID_ORIGIN ?? 'https://adminportalmedico360.curseduca.pro';

export function EmbedAuthPage() {
  const navigate = useNavigate();

  const { fase, erro } = useIdentidadeWaid({
    apiBase: API_BASE,
    waidOrigin: WAID_ORIGIN,
    aoAutenticar: resposta => {
      setToken(resposta.access_token);
      navigate(resposta.onboarding_complete ? '/' : '/onboarding', { replace: true });
    },
  });

  // `<Navigate>` em vez de navegar dentro do efeito: o hook já cuidou do
  // redirecionamento no sucesso; isto só cobre um render extra.
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
          {/* A tela precisa dizer o que FAZER, não só que falhou. */}
          <p style={{ fontSize: 13, color: 'var(--pen2)', margin: '0 0 20px', lineHeight: 1.5 }}>
            {erro?.tipo === 'sem_iframe'
              // Caso conhecido: os aplicativos da Waid abrem a seção sem iframe,
              // e nesse contexto a plataforma não tem como nos dizer quem é o
              // médico. Aqui o login por e-mail não é contorno — é o caminho.
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
