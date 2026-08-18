import { FieldWidget } from '../../../components/FieldWidget';
import { Card, CardHeader, FieldGroup, Separator, SubHeading } from '../ui';
import { IconHeartPulse } from '../icons';
import { makeFieldVisibility, pickField } from '../visibility';
import type { StepProps } from './types';

export function AltoRiscoStep({ fields, formSpec, values, onChange, aiFilledKeys, fieldErrors, showErrors }: StepProps) {
  const isVisible = makeFieldVisibility(formSpec, 'alto_risco', values);

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
          icon={<IconHeartPulse size={18} color="var(--red)" />}
          iconColor="var(--red)"
          title="Doença aterosclerótica e marcadores"
          description="Marque as condições de alto risco presentes."
        />

        <SubHeading>Aterosclerose subclínica</SubHeading>
        <FieldGroup>
          {field('doenca_aterosclerotica_significativa')}
          {field('cac_ua')}
          {field('cac_percentil_gt75')}
          {field('placa_carotidea_lt50')}
          {field('placa_angiotc_lt50')}
          {field('aaa_conhecido')}
        </FieldGroup>

        <Separator />

        <SubHeading>Marcadores lipídicos</SubHeading>
        <FieldGroup>
          {field('ldl_mgdl')}
          {field('lpa_mgdl')}
          {field('lpa_nmol')}
          {field('hipercolesterolemia_familiar')}
        </FieldGroup>
      </Card>
    </div>
  );
}
