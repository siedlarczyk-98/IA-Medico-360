import { Card, CardHeader, Button } from '../ui';
import { IconTrendingUp, IconChevronRight, IconChevronLeft } from '../icons';
import type { RiskLevel } from '../riskTypes';
import type { WizardStepProps } from './types';

/** Porta literal de `Step5Aggravating.tsx` (app de referência). */

interface AggravatingCategory {
  title: string;
  items: string[];
}

const AGGRAVATING_CATEGORIES: AggravatingCategory[] = [
  {
    title: 'História familiar de doença cardiovascular prematura',
    items: [
      'Parente de 1º grau com evento em idade < 55 anos (sexo masculino) ou < 65 anos (sexo feminino)',
    ],
  },
  {
    title: 'Adiposidade e suas manifestações',
    items: [
      'Adiposidade',
      'Esteatose hepática, especialmente formas mais graves (por exemplo, com fibrose) ou associada a fatores cardiometabólicos',
      'Síndrome metabólica',
    ],
  },
  {
    title: 'Condições inflamatórias crônicas',
    items: [
      'Artrite reumatoide',
      'Psoríase',
      'Lúpus eritematoso sistêmico',
      'Doenças inflamatórias intestinais (retocolite ulcerativa e doença de Crohn)',
      'Infecção crônica pelo HIV',
    ],
  },
  {
    title: 'Transplantes',
    items: ['Transplante de órgãos (por exemplo, coração, fígado, rim)'],
  },
  {
    title: 'Fatores agravantes de risco específicos das mulheres',
    items: [
      'Menarca precoce (≤ 12 anos) ou tardia (≥ 17 anos)',
      'Distúrbios durante a gestação (pré-eclâmpsia, eclâmpsia, hipertensão gestacional, diabetes gestacional)',
      'Parto prematuro',
      'Restrição de crescimento intrauterino',
      'Abortos de repetição (≥ 3 perdas gestacionais espontâneas)',
      'Menopausa precoce (< 40 anos)',
    ],
  },
  {
    title: 'Marcadores',
    items: [
      'Lipoproteína(a) ≥ 50 mg/dL ou ≥ 125 nmol/L',
      'Proteína C-reativa ultrassensível ≥ 2,0 mg/L',
    ],
  },
];

function reclassify(current: RiskLevel, hasAggravants: boolean): RiskLevel {
  if (!hasAggravants) return current;
  if (current === 'low') return 'intermediate';
  if (current === 'intermediate') return 'high';
  return current;
}

interface AgravantesStepProps extends Omit<WizardStepProps, 'onResult' | 'onNext'> {
  currentRisk: RiskLevel;
  onResult: (level: RiskLevel) => void;
}

export function AgravantesStep({ state, currentRisk, onChange, onResult, onBack }: AgravantesStepProps) {
  const toggleFactor = (item: string) => {
    const current = state.aggravatingFactors;
    const updated = current.includes(item) ? current.filter(i => i !== item) : [...current, item];
    onChange({ aggravatingFactors: updated });
  };

  const hasAggravants = state.aggravatingFactors.length > 0;
  const finalRisk = reclassify(currentRisk, hasAggravants);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader
          icon={<IconTrendingUp size={18} color="var(--warning)" />}
          iconColor="var(--warning)"
          title="Fatores agravantes (reclassificação)"
          description="Marque os fatores agravantes presentes. A presença de agravantes reclassifica o risco um nível acima."
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {AGGRAVATING_CATEGORIES.map(category => (
            <div key={category.title}>
              <h4 style={{ fontSize: 12, fontWeight: 700, color: 'var(--pen2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                {category.title}
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {category.items.map(item => (
                  <label
                    key={item}
                    style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 10px', borderRadius: 8, cursor: 'pointer' }}
                  >
                    <input
                      type="checkbox"
                      checked={state.aggravatingFactors.includes(item)}
                      onChange={() => toggleFactor(item)}
                      style={{ marginTop: 3, width: 16, height: 16, flexShrink: 0, accentColor: 'var(--petrol)' }}
                    />
                    <span style={{ fontSize: 13.5, color: 'var(--ink)', lineHeight: 1.4 }}>{item}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
          <div style={{ padding: '12px 14px', borderRadius: 8, background: 'var(--fill2)', fontSize: 13 }}>
            Agravantes selecionados: <strong>{state.aggravatingFactors.length}</strong>
            {hasAggravants && currentRisk !== finalRisk && (
              <span style={{ marginLeft: 8, color: 'var(--risk-high)', fontWeight: 700 }}>→ Risco reclassificado</span>
            )}
          </div>
        </div>
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="outline" onClick={onBack}>
          <IconChevronLeft size={16} /> Voltar
        </Button>
        <Button onClick={() => onResult(finalRisk)}>
          Ver Resultado Final <IconChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
