import { FieldWidget } from '../../../components/FieldWidget';
import { Card, CardHeader, FieldGroup } from '../ui';
import { IconTrendingUp } from '../icons';
import { makeFieldVisibility, pickField } from '../visibility';
import type { StepProps } from './types';

export function AgravantesStep({ fields, formSpec, values, onChange, aiFilledKeys, fieldErrors, showErrors }: StepProps) {
  const isVisible = makeFieldVisibility(formSpec, 'agravantes', values);

  const field = (key: string) => {
    const def = pickField(fields, key);
    if (!def || !isVisible(key)) return null;
    return (
      <FieldWidget
        key={key}
        field={def}
        value={values[key]}
        onChange={v => onChange(key, v)}
        aiPrefilled={aiFilledKeys?.has(key)}
        error={fieldErrors?.[key]}
        showError={showErrors}
      />
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader
          icon={<IconTrendingUp size={18} color="var(--warning)" />}
          iconColor="var(--warning)"
          title="Fatores agravantes (reclassificação)"
          description="A presença de agravantes pode reclassificar o risco para a categoria imediatamente acima."
        />
        <FieldGroup>
          {field('historia_familiar_cv_prematura')}
          {field('adiposidade_com_param_alterado')}
          {field('esteatose_hepatica')}
          {field('doenca_inflamatoria_cronica')}
          {field('transplante_orgao_solido')}
          {field('fatores_femininos')}
          {field('pcr_us_mgL')}
        </FieldGroup>
      </Card>
    </div>
  );
}
