import { useNavigate } from 'react-router-dom';
import { useCalculatorDetail } from '../hooks/useCalculatorDetail';
import { CalculatorTopbar } from '../components/CalculatorTopbar';
import { PreventForm } from '../calculators/prevent/PreventForm';

const SLUG = 'prevent_aha2024';

/**
 * Calculadora PREVENT avulsa. O mesmo escore que o wizard SBC 2025 usa no
 * Step4, sem o fluxograma da SBC em volta — ver `calculators/prevent/PreventForm.tsx`
 * para por que a classificação de risco não aparece aqui.
 *
 * Só chama `POST /prevent/calculate`; não persiste execução nem audit log.
 */
export function PreventPage() {
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
        title={calculator?.name ?? 'PREVENT (AHA 2024)'}
        subtitle="Risco cardiovascular em 10 e 30 anos"
        onBack={() => navigate('/')}
      />

      <div style={{ maxWidth: 780, margin: '0 auto', padding: '24px 16px 60px' }}>
        <PreventForm />
      </div>
    </div>
  );
}
