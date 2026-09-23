import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { OnboardingGate } from '@shared/onboarding/OnboardingGate';
import { getToken, isAuthenticated, isTokenExpired, setToken } from './lib/auth';
import { useSessaoViva } from './lib/useSessaoViva';
import { useChatController } from './chat/useChatController';
import { DesktopShell } from './shell/desktop/DesktopShell';
import { cascaMovelDisponivel, useLayout } from './shell/layout';

// Mesma convenção dos módulos de `api/`: o backend por env, sem barra final.
const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

// Páginas de auth são carregadas sob demanda (não fazem parte da rota principal).
const LoginPage = lazy(() => import('./pages/LoginPage').then(m => ({ default: m.LoginPage })));
const InvitePage = lazy(() => import('./pages/InvitePage').then(m => ({ default: m.InvitePage })));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage').then(m => ({ default: m.OnboardingPage })));
const RegisterPage = lazy(() => import('./pages/RegisterPage').then(m => ({ default: m.RegisterPage })));
const EmbedAuthPage = lazy(() => import('./pages/EmbedAuthPage').then(m => ({ default: m.EmbedAuthPage })));
// Tela técnica, sem link em lugar nenhum: só é alcançada por quem digita a rota
// ou por uma seção da Waid apontada para ela. Ver o docblock do arquivo.
const DiagnosticoEmbedPage = lazy(() => import('./pages/DiagnosticoEmbedPage').then(m => ({ default: m.DiagnosticoEmbedPage })));

// Casca mobile sob demanda: quem só usa no computador não baixa o código dela.
const carregarCascaMovel = () => import('./shell/mobile/MobileShell');
const MobileShell = lazy(carregarCascaMovel);

// Pré-carrega quando o navegador estiver ocioso. Sem isto, a primeira rotação
// do celular (ou o primeiro redimensionar da janela) mostraria a tela em branco
// enquanto o código da casca chega pela rede.
if (cascaMovelDisponivel() && typeof window !== 'undefined') {
  const ocioso = window.requestIdleCallback ?? ((fn: () => void) => setTimeout(fn, 1500));
  ocioso(() => { void carregarCascaMovel(); });
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated() || isTokenExpired()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/**
 * O estado do chat mora AQUI, acima da casca, e não dentro dela. Ver o docblock
 * de `useChatController`: a casca pode ser trocada (desktop ↔ mobile) sem que a
 * resposta em andamento morra junto.
 *
 * O `Suspense` também fica aqui, ABAIXO do controller. Sem ele, a casca mobile
 * (carregada sob demanda) suspenderia até o `Suspense` das rotas, que esconde o
 * app inteiro — conversa e stream incluídos — até o código chegar.
 */
function MainApp() {
  // Renova o token ao voltar do segundo plano. Antes disto, minimizar o app por
  // mais de uma hora derrubava o médico no login.
  useSessaoViva();
  const chat = useChatController();
  const layout = useLayout();
  return (
    <Suspense fallback={null}>
      {layout === 'mobile' ? <MobileShell chat={chat} /> : <DesktopShell chat={chat} />}
    </Suspense>
  );
}

function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/cadastro" element={<RegisterPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/invite" element={<InvitePage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/embed-auth" element={<EmbedAuthPage />} />
        <Route path="/diagnostico-embed" element={<DiagnosticoEmbedPage />} />
        <Route path="/" element={
          <RequireAuth>
            {/*
              O gate lê `onboarding_pendencias` do servidor — nenhum app decide
              o que falta. Fica AQUI, e não só no /login, porque antes a decisão
              acontecia apenas no momento do login: bastava navegar direto para
              "/" para pular o onboarding inteiro.
            */}
            <OnboardingGate
              apiBase={API_BASE}
              token={getToken()}
              aoConcluir={t => { setToken(t); window.location.reload(); }}
            >
              <MainApp />
            </OnboardingGate>
          </RequireAuth>
        } />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
