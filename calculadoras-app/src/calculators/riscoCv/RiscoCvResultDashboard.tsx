import { DISCLAIMER } from '../../tokens';
import { IconShieldAlert, IconAlertTriangle, IconTarget, IconTrendingDown, IconPill, IconRestart } from './icons';
import { RISK_GOALS, RISK_LABELS, type RiskLevel } from './riskTypes';

interface Props {
  riskLevel: RiskLevel;
  onRestart: () => void;
}

const RISK_CONFIG: Record<RiskLevel, { bg: string; color: string; border: string }> = {
  low:           { bg: 'var(--risk-low-bg)',          color: 'var(--risk-low)',          border: 'var(--risk-low-border)' },
  intermediate:  { bg: 'var(--risk-intermediate-bg)', color: 'var(--risk-intermediate)', border: 'var(--risk-intermediate-border)' },
  high:          { bg: 'var(--risk-high-bg)',          color: 'var(--risk-high)',          border: 'var(--risk-high-border)' },
  'very-high':   { bg: 'var(--risk-very-high-bg)',     color: 'var(--risk-very-high)',     border: 'var(--risk-very-high-border)' },
  extreme:       { bg: 'var(--risk-extreme-bg)',       color: 'var(--risk-extreme)',       border: 'var(--risk-extreme-border)' },
};

const cardStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid var(--line)',
  borderRadius: 12,
  boxShadow: '0 1px 2px rgba(14,37,45,0.05)',
};

function GoalCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div style={{ ...cardStyle, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 600, color: 'var(--pen2)' }}>
        {icon} {label}
      </span>
      <span style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.25 }}>{value}</span>
    </div>
  );
}

/** Porta estrutural de `ResultDashboard.tsx` (app de referência). */
export function RiscoCvResultDashboard({ riskLevel, onRestart }: Props) {
  const cfg = RISK_CONFIG[riskLevel];
  const goal = RISK_GOALS[riskLevel];
  const label = RISK_LABELS[riskLevel];
  const isSevere = riskLevel === 'very-high' || riskLevel === 'extreme';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      <div style={{ ...cardStyle, border: `2px solid ${cfg.border}`, padding: '28px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
        <div style={{ width: 64, height: 64, borderRadius: '50%', background: cfg.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {isSevere ? <IconAlertTriangle size={30} color={cfg.color} /> : <IconShieldAlert size={30} color={cfg.color} />}
        </div>
        <div>
          <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
            Categoria de Risco
          </p>
          <p style={{ fontSize: 30, fontWeight: 800, color: cfg.color, letterSpacing: '-0.01em' }}>
            Risco {label}
          </p>
        </div>
      </div>

      <div>
        <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
          Metas terapêuticas
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
          <GoalCard icon={<IconTarget size={14} />} label="Meta Primária – LDL-c" value={goal.ldlGoal} />
          <GoalCard icon={<IconTrendingDown size={14} />} label="Redução LDL-c" value={goal.ldlReduction} />
          <GoalCard icon={<IconTarget size={14} />} label="Meta Coprimária – Não-HDL-c" value={goal.nonHdlGoal} />
        </div>
        {goal.apoB && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12, marginTop: 12 }}>
            <GoalCard icon={<IconTarget size={14} />} label="Meta Secundária – ApoB" value={goal.apoB} />
          </div>
        )}
      </div>

      <div style={{ ...cardStyle, padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>
          <IconPill size={17} color="var(--petrol)" /> Recomendações farmacológicas
        </span>
        <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {goal.pharmacotherapy.map((rec, i) => (
            <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 13.5, color: 'var(--pen)' }}>
              <span style={{ flexShrink: 0, marginTop: 6, width: 6, height: 6, borderRadius: '50%', background: cfg.color, display: 'inline-block' }} />
              {rec}
            </li>
          ))}
        </ul>
      </div>

      <p style={{ fontSize: 11.5, color: 'var(--pen3)', textAlign: 'center', padding: '4px 12px' }}>
        {DISCLAIMER}
      </p>

      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 4 }}>
        <button
          type="button"
          onClick={onRestart}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 20px',
            background: '#fff',
            color: 'var(--pen)',
            border: '1px solid var(--line)',
            borderRadius: 10,
            fontSize: 13.5,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          <IconRestart size={15} /> Reiniciar calculadora
        </button>
      </div>
    </div>
  );
}
