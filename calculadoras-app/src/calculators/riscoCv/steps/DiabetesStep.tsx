import { FieldWidget } from '../../../components/FieldWidget';
import { Card, CardHeader, FieldGroup, Separator, SubHeading } from '../ui';
import { IconStethoscope } from '../icons';
import { makeFieldVisibility, pickField } from '../visibility';
import type { StepProps } from './types';

export function DiabetesStep({ fields, formSpec, values, onChange, aiFilledKeys, fieldErrors, showErrors }: StepProps) {
  const isVisible = makeFieldVisibility(formSpec, 'diabetes', values);

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

  const hasDM = values.diabetes === true;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader icon={<IconStethoscope size={18} />} title="Diabetes mellitus" description="O paciente possui diagnóstico de Diabetes Mellitus?" />
        <FieldGroup>
          {field('diabetes')}
        </FieldGroup>
      </Card>

      {hasDM && (
        <Card accentColor="var(--mint)">
          <CardHeader
            icon={<IconStethoscope size={18} color="var(--petrol)" />}
            title="Estratificadores — Diabetes"
            description="Classificam o paciente com DM como muito alto, alto ou intermediário risco (EAR/EMAR renais, cardiovasculares e microvasculares)."
          />

          <SubHeading>Perfil e duração</SubHeading>
          <FieldGroup>
            {field('tipo_dm')}
            {field('duracao_dm_anos')}
            {field('dm1_diagnosticado_apos_18_anos')}
          </FieldGroup>

          <Separator />

          <SubHeading>Marcadores de risco</SubHeading>
          <FieldGroup>
            {field('historia_familiar_dac_prematura')}
            {field('sindrome_metabolica')}
            {field('albuminuria_mg_g')}
          </FieldGroup>

          <Separator />

          <SubHeading>Complicações microvasculares</SubHeading>
          <FieldGroup>
            {field('neuropatia_autonoma_incipiente')}
            {field('neuropatia_autonoma_instalada')}
            {field('retinopatia_np_leve')}
            {field('retinopatia_avancada')}
          </FieldGroup>
        </Card>
      )}
    </div>
  );
}
