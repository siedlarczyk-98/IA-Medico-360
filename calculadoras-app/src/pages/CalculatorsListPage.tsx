import { useNavigate } from 'react-router-dom';
import { useCalculators } from '../hooks/useCalculators';
import { CalculatorCard } from '../components/CalculatorCard';
import { useCurrentUser } from '../lib/useCurrentUser';
import { logout } from '../lib/auth';

export function CalculatorsListPage() {
  const { data: calculators, isLoading, error } = useCalculators('cardiologia');
  const user = useCurrentUser();
  const navigate = useNavigate();

  return (
    <div style={{ minHeight: '100vh', background: 'var(--fill2)' }}>
      {/* Topbar */}
      <div style={{
        background: '#fff',
        borderBottom: '1px solid var(--line)',
        padding: '0 24px',
        height: 56,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: 'var(--mint)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
              <path d="M9 12l2 2 4-4m-5-7H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V9l-5-5z" stroke="var(--petrol)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>Calculadoras Clínicas</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {user && (
            <span style={{ fontSize: 12, color: 'var(--pen2)' }}>
              {user.firstName ?? user.email}
            </span>
          )}
          <button
            type="button"
            onClick={logout}
            style={{
              fontSize: 12,
              color: 'var(--pen3)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '4px 8px',
            }}
          >
            Sair
          </button>
        </div>
      </div>

      {/* Conteúdo */}
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '32px 20px' }}>
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--ink)', marginBottom: 6 }}>
            Calculadoras
          </h1>
          <p style={{ fontSize: 13, color: 'var(--pen2)' }}>
            Ferramentas de apoio à decisão clínica baseadas em diretrizes.
          </p>
        </div>

        {/* Filtro de especialidade */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          <button
            type="button"
            onClick={() => navigate('/')}
            style={{
              padding: '6px 14px',
              borderRadius: 20,
              border: '1px solid var(--petrol)',
              background: 'var(--petrol)',
              color: '#fff',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Cardiologia
          </button>
        </div>

        {isLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2].map(i => (
              <div key={i} style={{ height: 90, borderRadius: 14, background: 'var(--fill)', animation: 'pulse 1.4s ease-in-out infinite' }} />
            ))}
          </div>
        )}

        {error && (
          <p style={{ fontSize: 13, color: 'var(--red)', background: 'var(--red-bg)', padding: '12px 14px', borderRadius: 10 }}>
            Erro ao carregar calculadoras: {error instanceof Error ? error.message : 'Tente novamente.'}
          </p>
        )}

        {calculators && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {calculators.map(c => (
              <CalculatorCard key={c.id} calculator={c} />
            ))}
            {calculators.length === 0 && (
              <p style={{ fontSize: 13, color: 'var(--pen2)', textAlign: 'center', padding: 40 }}>
                Nenhuma calculadora disponível.
              </p>
            )}
          </div>
        )}
      </div>

      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
      `}</style>
    </div>
  );
}
