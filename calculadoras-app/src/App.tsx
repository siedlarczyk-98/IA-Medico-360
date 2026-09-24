import { lazy, Suspense, useEffect } from 'react';
import { Navigate, Route, Routes, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { OnboardingGate } from '@shared/onboarding/OnboardingGate';
import { useSessaoViva } from '@shared/embed/sessao';
import { TelaDeEspera } from '@shared/embed/TelaDeEspera';
import { getToken, isTokenExpired, sessaoExpirou, setToken } from './lib/auth';
import { getMe } from './api/auth';

// Mesma convenção de `api/auth.ts`: vazio em dev (o proxy do Vite cuida do
// CORS), domínio do backend em produção.
const API_BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '';

// Side-effect: registra os formSpecs das calculadoras genéricas.
import './calculators';

const LoginPage = lazy(() => import('./pages/LoginPage').then(m => ({ default: m.LoginPage })));
const EmbedAuthPage = lazy(() => import('./pages/EmbedAuthPage').then(m => ({ default: m.EmbedAuthPage })));
const CalculatorsListPage = lazy(() => import('./pages/CalculatorsListPage').then(m => ({ default: m.CalculatorsListPage })));
const RiscoCvSbc2025Page = lazy(() => import('./pages/RiscoCvSbc2025Page').then(m => ({ default: m.RiscoCvSbc2025Page })));
const PreventPage = lazy(() => import('./pages/PreventPage').then(m => ({ default: m.PreventPage })));
const GenericCalculatorPage = lazy(() => import('./pages/GenericCalculatorPage').then(m => ({ default: m.GenericCalculatorPage })));

function LoadingScreen() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--fill2)',
    }}>
      <p style={{ fontSize: 'var(--texto-apoio)', color: 'var(--pen2)' }}>Carregando…</p>
    </div>
  );
}

/**
 * Sessão acabou: entra de novo (pela Waid quando hospedado, senão login).
 * Efeito e não chamada no render — `sessaoExpirou` navega e grava estado.
 */
function Reentrar() {
  useEffect(() => { sessaoExpirou(); }, []);
  return <TelaDeEspera mensagem="Renovando sua sessão…" />;
}

/**
 * Uma tela NOVA por calculadora. Sem a `key`, ir de uma calculadora genérica
 * direto para outra (link, voltar/avançar) reaproveitava o componente e os
 * valores digitados continuavam lá: um campo com o mesmo nome — idade, creatinina
 * — chegava preenchido com o dado do paciente anterior.
 */
function CalculadoraGenerica() {
  const { slug } = useParams<{ slug: string }>();
  return <GenericCalculatorPage key={slug} />;
}

function CookieAuthCheck({ children }: { children: React.ReactNode }) {
  const { isSuccess, isError, isPending } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getMe,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  if (isPending) return <LoadingScreen />;
  if (isError && !isSuccess) return <Reentrar />;
  return <>{children}</>;
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  // O gate entra aqui, num lugar só, e vale para todas as rotas — antes este
  // app ignorava `onboarding_complete` por completo (o EmbedAuthPage mandava
  // direto para "/"), então dava para usar as calculadoras sem nunca ter
  // preenchido nada.
  //
  // `modo="avisar"` de propósito: mostra faixa e deixa passar. Bloquear uma
  // calculadora de creatinina porque falta CRM é hostil e não melhora o dado —
  // no app de notícias bloquear se justifica, porque lá o perfil é o que define
  // o que ele vai ler.
  //
  // E avisa SÓ sobre o aceite dos Termos: as calculadoras não filtram nada por
  // especialidade (o `?specialty=` da lista é escolha do usuário, não vem do
  // perfil), então cobrar o perfil aqui prometendo "conteúdo da sua
  // especialidade" seria prometer o que este app não entrega. O aceite é outra
  // coisa — é LGPD, e vale em qualquer tela.
  const conteudo = (
    <OnboardingGate
      apiBase={API_BASE}
      token={getToken()}
      modo="avisar"
      avisarSobre={['aceite_termos']}
      aoConcluir={t => { setToken(t); window.location.reload(); }}
    >
      {children}
    </OnboardingGate>
  );
  const token = getToken();
  if (token && !isTokenExpired()) return conteudo;
  // Token guardado e VENCIDO não passa pelo `CookieAuthCheck`: ele consultava
  // `['currentUser']`, que o cache ainda tinha da sessão morta, e deixava a
  // tela abrir para toda chamada seguinte levar 401. O cookie também não é
  // reserva aqui — o backend lê o header antes do cookie, e no app nativo o
  // cookie da API é de terceiros.
  if (token) return <Reentrar />;
  return <CookieAuthCheck>{conteudo}</CookieAuthCheck>;
}

function App() {
  // Renova o token antes de vencer; se o app volta do segundo plano com ele já
  // vencido, entra de novo. Ver `shared/embed/sessao.ts`.
  useSessaoViva({ apiBase: API_BASE, getToken, setToken, aoExpirar: sessaoExpirou });
  return (
    <Suspense fallback={<LoadingScreen />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/embed-auth" element={<EmbedAuthPage />} />
        <Route path="/" element={<RequireAuth><CalculatorsListPage /></RequireAuth>} />
        <Route path="/calculadoras/risco-cv-sbc2025" element={<RequireAuth><RiscoCvSbc2025Page /></RequireAuth>} />
        <Route path="/calculadoras/prevent" element={<RequireAuth><PreventPage /></RequireAuth>} />
        <Route path="/calculadoras/:slug" element={<RequireAuth><CalculadoraGenerica /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
