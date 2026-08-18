import type { ExecuteResponse, RiscoCvResult } from '../../api/calculators';
import { DISCLAIMER } from '../../tokens';
import { IconShieldAlert, IconAlertTriangle, IconTarget, IconTrendingDown, IconPill } from './icons';
import { RISK_GOALS } from './riskGoals';

interface Props {
  result: ExecuteResponse;
}

const CATEGORIA_CONFIG: Record<RiscoCvResult['categoria'], { label: string; bg: string; color: string; border: string }> = {
  BAIXO:        { label: 'Risco Baixo',         bg: '#dcfce7', color: '#15803d', border: '#86efac' },
  INTERMEDIARIO: { label: 'Risco Intermediário', bg: '#fef9c3', color: '#a16207', border: '#fde047' },
  ALTO:         { label: 'Risco Alto',           bg: '#ffedd5', color: '#c2410c', border: '#fb923c' },
  MUITO_ALTO:   { label: 'Risco Muito Alto',     bg: '#fee2e2', color: '#b91c1c', border: '#f87171' },
  EXTREMO:      { label: 'Risco Extremo',        bg: '#fee2e2', color: '#7f1d1d', border: '#dc2626' },
};

const FATOR_LABEL: Record<string, string> = {
  historia_familiar_cv_prematura: 'História familiar de DCV prematura (1º grau)',
  adiposidade:                    'Adiposidade com parâmetro antropométrico alterado',
  esteatose_hepatica:             'Esteatose hepática (especialmente formas graves/com fibrose)',
  sindrome_metabolica:            'Síndrome metabólica',
  doenca_inflamatoria_cronica:    'Doença inflamatória crônica (AR, psoríase, LES, DII, HIV)',
  transplante_orgao_solido:       'Transplante de órgão sólido',
  fatores_femininos:              'Fatores específicos femininos',
  lipoproteina_a_elevada:         'Lipoproteína(a) elevada (≥ 50 mg/dL ou ≥ 125 nmol/L)',
  pcr_us_elevada:                 'PCR-ultrassensível elevada (≥ 2,0 mg/L)',
};

const PREVENT_LABEL: Record<string, string> = {
  ascvd_10a: 'ASCVD em 10 anos',
  cvd_10a:   'DCV total em 10 anos',
  hf_10a:    'IC em 10 anos',
  ascvd_30a: 'ASCVD em 30 anos',
  cvd_30a:   'DCV total em 30 anos',
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
      <span style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.25, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{value}</span>
    </div>
  );
}

export function RiscoCvResultDashboard({ result }: Props) {
  const r = result.result as unknown as RiscoCvResult;
  const cfg = CATEGORIA_CONFIG[r.categoria];
  const goal = RISK_GOALS[r.categoria];
  const preventEntries = Object.entries(r.prevent ?? {}) as [string, number][];
  const isSevere = r.categoria === 'MUITO_ALTO' || r.categoria === 'EXTREMO';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Banner de categoria */}
      <div style={{ ...cardStyle, border: `2px solid ${cfg.border}`, padding: '28px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
        <div style={{
          width: 64, height: 64, borderRadius: '50%',
          background: cfg.bg, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: cfg.color,
        }}>
          {isSevere ? <IconAlertTriangle size={30} color={cfg.color} /> : <IconShieldAlert size={30} color={cfg.color} />}
        </div>
        <div>
          <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
            Estratificação de Risco CV — SBC 2025
          </p>
          <p style={{ fontSize: 30, fontWeight: 800, color: cfg.color, letterSpacing: '-0.01em' }}>
            {cfg.label}
          </p>
        </div>
        <div style={{
          background: cfg.color, color: '#fff', borderRadius: 999, padding: '5px 14px',
          fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em',
        }}>
          Passo {r.passo_determinante}
        </div>
      </div>

      {/* Metas terapêuticas */}
      <div>
        <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
          Metas terapêuticas
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
          <GoalCard icon={<IconTarget size={14} />} label="LDL-c" value={r.meta_ldl_recomendada || goal.ldlGoal} />
          <GoalCard icon={<IconTrendingDown size={14} />} label="Redução LDL-c" value={goal.ldlReduction} />
          <GoalCard icon={<IconTarget size={14} />} label="Não-HDL-c" value={goal.nonHdlGoal} />
        </div>
        {goal.apoB && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12, marginTop: 12 }}>
            <GoalCard icon={<IconTarget size={14} />} label="ApoB" value={goal.apoB} />
          </div>
        )}
      </div>

      {/* Recomendações farmacológicas */}
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

      {/* Scores PREVENT */}
      {preventEntries.length > 0 && (
        <div>
          <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
            Escore PREVENT (AHA)
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12 }}>
            {preventEntries.map(([key, val]) => (
              <div key={key} style={{ ...cardStyle, padding: '14px 16px' }}>
                <p style={{ fontSize: 11.5, color: 'var(--pen2)', marginBottom: 4 }}>{PREVENT_LABEL[key] ?? key}</p>
                <p style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)' }}>{val}%</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Fatores agravantes */}
      {r.fatores_agravantes.length > 0 && (
        <div style={{ ...cardStyle, padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>
            Fatores agravantes presentes
          </span>
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {r.fatores_agravantes.map(k => (
              <li key={k} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 13.5, color: 'var(--pen)' }}>
                <span style={{ flexShrink: 0, marginTop: 6, width: 6, height: 6, borderRadius: '50%', background: 'var(--red)', display: 'inline-block' }} />
                {FATOR_LABEL[k] ?? k}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Disclaimer */}
      <p style={{ fontSize: 11.5, color: 'var(--pen3)', textAlign: 'center', padding: '4px 12px' }}>
        {DISCLAIMER}
      </p>
    </div>
  );
}
