import { useNavigate } from 'react-router-dom';
import { useCalculatorDetail } from '../hooks/useCalculatorDetail';
import { CalculatorTopbar } from '../components/CalculatorTopbar';
import { RiskCalculator } from '../calculators/riscoCv/RiskCalculator';

const SLUG = 'risco_cv_sbc2025';

/**
 * Wizard 100% client-side, porta literal do app de referência do usuário —
 * ver `calculadoras-app/src/calculators/riscoCv/RiskCalculator.tsx`. O backend só é
 * chamado (em `dry_run`) para calcular o escore PREVENT no Step4; toda a
 * classificação de risco é derivada localmente, sem persistir execução/audit log.
 */
export function RiscoCvSbc2025Page() {
  const navigate = useNavigate();
  const { data: calculator, isLoading } = useCalculatorDetail(SLUG);

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--fill2)' }}>
        <p style={{ fontSize: 14, color: 'var(--pen2)' }}>Carregando calculadora…</p>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--fill2)' }}>
      <CalculatorTopbar
        title={calculator?.name ?? 'Risco Cardiovascular — SBC 2025'}
        subtitle="Fluxograma SBC 2025"
        onBack={() => navigate('/')}
      />

      <div style={{ maxWidth: 780, margin: '0 auto', padding: '24px 16px 60px' }}>
        <RiskCalculator />
      </div>
    </div>
  );
}
