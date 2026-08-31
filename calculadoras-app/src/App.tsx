import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { isAuthenticated, isTokenExpired } from './lib/auth';
import { getMe } from './api/auth';

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
      <p style={{ fontSize: 14, color: 'var(--pen2)' }}>Carregando…</p>
    </div>
  );
}

function CookieAuthCheck({ children }: { children: React.ReactNode }) {
  const { isSuccess, isError, isPending } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getMe,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  if (isPending) return <LoadingScreen />;
  if (isError && !isSuccess) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (isAuthenticated() && !isTokenExpired()) return <>{children}</>;
  return <CookieAuthCheck>{children}</CookieAuthCheck>;
}

function App() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/embed-auth" element={<EmbedAuthPage />} />
        <Route path="/" element={<RequireAuth><CalculatorsListPage /></RequireAuth>} />
        <Route path="/calculadoras/risco-cv-sbc2025" element={<RequireAuth><RiscoCvSbc2025Page /></RequireAuth>} />
        <Route path="/calculadoras/prevent" element={<RequireAuth><PreventPage /></RequireAuth>} />
        <Route path="/calculadoras/:slug" element={<RequireAuth><GenericCalculatorPage /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
