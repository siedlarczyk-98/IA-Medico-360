import { Card, CardHeader, CheckItem, Button } from '../ui';
import { IconHeartPulse, IconChevronRight, IconChevronLeft } from '../icons';
import type { WizardStepProps } from './types';

/** Porta literal de `Step3HighRisk.tsx` (app de referência). */

export function AltoRiscoStep({ state, onChange, onResult, onNext, onBack }: WizardStepProps) {
  const hasHighRisk = state.ateroscleroseSubclinica || state.ldl190 || state.lpa180 || state.cac100a300;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader
          icon={<IconHeartPulse size={18} color="var(--risk-high)" />}
          iconColor="var(--risk-high)"
          title="Condições de alto risco"
          description="Marque se alguma condição de alto risco está presente."
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <CheckItem
            checked={state.ateroscleroseSubclinica}
            onChange={v => onChange({ ateroscleroseSubclinica: v })}
            label="Aterosclerose subclínica"
            description="Placa carotídea ou femoral, aneurisma de aorta abdominal"
          />
          <CheckItem
            checked={state.ldl190}
            onChange={v => onChange({ ldl190: v })}
            label="LDL-c ≥ 190 mg/dL"
          />
          <CheckItem
            checked={state.lpa180}
            onChange={v => onChange({ lpa180: v })}
            label="Lp(a) > 180 mg/dL (ou > 390 nmol/L)"
          />
          <CheckItem
            checked={state.cac100a300}
            onChange={v => onChange({ cac100a300: v })}
            label="CAC entre 100 e 300 UA"
          />
        </div>
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="outline" onClick={onBack}>
          <IconChevronLeft size={16} /> Voltar
        </Button>
        <Button onClick={() => (hasHighRisk ? onResult('high') : onNext())}>
          {hasHighRisk ? 'Ver Resultado (Alto)' : 'Próximo'} <IconChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
