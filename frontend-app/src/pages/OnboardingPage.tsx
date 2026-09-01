/**
 * Rota `/onboarding` do app principal.
 *
 * O formulário em si NÃO mora mais aqui — mora em `shared/onboarding`, escrito
 * uma vez e renderizado pelos três apps. Esta página sobrou como porta de
 * entrada nomeada, porque o `EmbedAuthPage` e o `LoginPage` redirecionam para
 * ela, e porque links antigos apontam para cá.
 *
 * O QUE SAIU DAQUI, E POR QUÊ
 *
 * 1. A lista de 55 especialidades, que era hardcoded neste arquivo. Ela era a
 *    ÚNICA lista canônica do produto — a ponto de `tests/test_news_taxonomia.py`
 *    precisar ler este TSX com regex para validar o backend. Agora vive em
 *    `app/medicina/especialidades.py` e é servida por `GET /meta/especialidades`.
 *
 * 2. A pergunta da especialidade. Ela chega sozinha: do cadastro (webhook) ou
 *    dos grupos `[CFM]` da Curseduca. Perguntar de novo era pedir para o médico
 *    digitar o que já sabíamos — e ele nem pode alterar depois, porque o campo é
 *    identidade profissional e vai definir acesso a conteúdo pago.
 *
 * 3. As regras de "o que é obrigatório". Quem decide é o servidor, em
 *    `identidade.pendencias()`, que conhece o estado real do usuário e não pede
 *    duas vezes o que já está preenchido.
 *
 * Sobrou o que nenhuma fonte automática tem: o momento da carreira (o grupo não
 * distingue residente de especialista) e o aceite dos Termos.
 */

import { Navigate, useNavigate } from 'react-router-dom';

import { OnboardingGate } from '@shared/onboarding/OnboardingGate';

import { getToken, isAuthenticated, setToken } from '../lib/auth';

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export function OnboardingPage() {
  const navigate = useNavigate();

  // `<Navigate>` em vez de chamar `navigate()` durante o render: navegar e
  // efeito colateral, e efeito colateral no corpo do componente e justamente o
  // que o React proibe.
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <OnboardingGate
      apiBase={API_BASE}
      token={getToken()}
      aoConcluir={token => {
        setToken(token);
        navigate('/', { replace: true });
      }}
    >
      {/* Sem pendências, esta rota não tem o que mostrar. */}
      <Navigate to="/" replace />
    </OnboardingGate>
  );
}
