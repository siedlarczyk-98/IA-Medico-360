import type { ExecuteResponse, RiscoCvResult } from '../api/calculators';
import { DISCLAIMER } from '@medico360/shared/tokens';

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

export function ResultPanel({ result }: Props) {
  const r = result.result as unknown as RiscoCvResult;
  const cfg = CATEGORIA_CONFIG[r.categoria];
  const preventEntries = Object.entries(r.prevent ?? {}) as [string, number][];

  return (
    <div style={{
      border: `2px solid ${cfg.border}`,
      borderRadius: 14,
      overflow: 'hidden',
    }}>
      {/* Cabeçalho — categoria */}
      <div style={{ background: cfg.bg, padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{
          flex: 1,
        }}>
          <p style={{ fontSize: 11, fontWeight: 700, color: cfg.color, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>
            Estratificação de Risco CV — SBC 2025
          </p>
          <p style={{ fontSize: 24, fontWeight: 800, color: cfg.color }}>
            {cfg.label}
          </p>
        </div>
        <div style={{
          background: cfg.color,
          color: '#fff',
          borderRadius: 10,
          padding: '8px 14px',
          fontSize: 12,
          fontWeight: 700,
          textAlign: 'center',
          whiteSpace: 'nowrap',
        }}>
          Passo {r.passo_determinante}
        </div>
      </div>

      <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20, background: '#fff' }}>

        {/* Meta LDL */}
        <div style={{ background: 'var(--fill2)', borderRadius: 10, padding: '14px 16px' }}>
          <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>Meta terapêutica</p>
          <p style={{ fontSize: 16, fontWeight: 700, color: 'var(--petrol)' }}>{r.meta_ldl_recomendada}</p>
        </div>

        {/* Interpretação */}
        {result.interpretation && (
          <p style={{ fontSize: 13, color: 'var(--pen)', lineHeight: 1.6 }}>{result.interpretation}</p>
        )}

        {/* Scores PREVENT */}
        {preventEntries.length > 0 && (
          <div>
            <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
              Escore PREVENT (AHA)
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 8 }}>
              {preventEntries.map(([key, val]) => (
                <div key={key} style={{ background: 'var(--fill2)', borderRadius: 8, padding: '10px 12px' }}>
                  <p style={{ fontSize: 11, color: 'var(--pen2)', marginBottom: 2 }}>{PREVENT_LABEL[key] ?? key}</p>
                  <p style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>{val}%</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Fatores agravantes */}
        {r.fatores_agravantes.length > 0 && (
          <div>
            <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Fatores agravantes presentes
            </p>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 5 }}>
              {r.fatores_agravantes.map(k => (
                <li key={k} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, color: 'var(--pen)' }}>
                  <span style={{ color: 'var(--red)', flexShrink: 0, marginTop: 1 }}>●</span>
                  {FATOR_LABEL[k] ?? k}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Disclaimer */}
        <p style={{ fontSize: 11, color: 'var(--pen3)', borderTop: '1px solid var(--line2)', paddingTop: 12 }}>
          {DISCLAIMER}
        </p>
      </div>
    </div>
  );
}
