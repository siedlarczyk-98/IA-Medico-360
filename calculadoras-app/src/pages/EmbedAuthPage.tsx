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

import { useEffect } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { montarOrigensWaid, useIdentidadeWaid } from '@shared/embed/identidade';
import { mensagemDaIdentidade, TelaDeEspera } from '@shared/embed/TelaDeEspera';

import { descartarSessaoDesteNavegador, setToken } from '../lib/auth';

// Mesma convenção de `api/auth.ts`: vazio em dev (o proxy do Vite cuida do
// CORS), domínio do backend em produção.
const API_BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '';
const WAID_ORIGIN =
  import.meta.env.VITE_WAID_ORIGIN ?? 'https://www.medico360.app';

/**
 * Duas origens, não uma: o embed no navegador responde do portal da Waid; o
 * app nativo responde do domínio público. Ver `montarOrigensWaid`.
 */
const ORIGENS_WAID = montarOrigensWaid(WAID_ORIGIN);

export function EmbedAuthPage() {
  const navigate = useNavigate();

  const { fase, erro } = useIdentidadeWaid({
    apiBase: API_BASE,
    waidOrigin: ORIGENS_WAID,
    aoAutenticar: resposta => {
      setToken(resposta.access_token);
      navigate('/', { replace: true });
    },
  });

  // Identidade não confirmada DENTRO do iframe: a sessão que já estava no
  // navegador não pode ser herdada. Ver `descartarSessaoDesteNavegador`.
  const tipoDoErro = fase === 'erro' ? erro?.tipo : undefined;
  useEffect(() => {
    if (tipoDoErro && tipoDoErro !== 'sem_iframe') descartarSessaoDesteNavegador();
  }, [tipoDoErro]);

  if (fase === 'pronto') return <Navigate to="/" replace />;

  // Esperando a Waid: a mesma tela nos três apps (`shared/embed/TelaDeEspera`).
  if (fase !== 'erro') return <TelaDeEspera mensagem={mensagemDaIdentidade(fase)} />;

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--fill2)',
    }}>
      <div style={{
        maxWidth: 380,
        textAlign: 'center',
        padding: 32,
        background: '#fff',
        border: '1px solid var(--line)',
        borderRadius: 16,
        boxShadow: '0 4px 24px rgba(14,37,45,0.07)',
      }}>
        <p style={{ fontSize: 'var(--texto-apoio)', color: 'var(--ink)', margin: '0 0 8px', fontWeight: 600 }}>
          {erro?.mensagem}
        </p>
        <p style={{ fontSize: 'var(--texto-apoio)', color: 'var(--pen2)', margin: '0 0 20px', lineHeight: 1.5 }}>
          {erro?.tipo === 'sem_iframe'
            // Caso conhecido: os aplicativos da Waid abrem a seção sem iframe,
            // e ali a plataforma não tem como nos dizer quem é o médico.
            ? 'No aplicativo, entre pelo seu e-mail. Pelo navegador, o acesso é automático.'
            : 'Você pode entrar pelo seu e-mail enquanto isso.'}
        </p>
        <button
          onClick={() => navigate('/login')}
          style={{
            fontSize: 'var(--texto-apoio)', color: 'var(--petrol)', background: 'none',
            border: '1px solid var(--line)', borderRadius: 8,
            padding: '8px 16px', cursor: 'pointer',
          }}
        >
          Entrar por e-mail
        </button>
      </div>
    </div>
  );
}
