import { FieldWidget } from '../../../components/FieldWidget';
import { Card, CardHeader, FieldGroup, Separator, SubHeading } from '../ui';
import { IconTarget } from '../icons';
import { makeFieldVisibility, pickField } from '../visibility';
import type { StepProps } from './types';

export function PreventStep({ fields, formSpec, values, onChange, aiFilledKeys, fieldErrors, showErrors }: StepProps) {
  const isVisible = makeFieldVisibility(formSpec, 'prevent', values);

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
          icon={<IconTarget size={18} />}
          title="Escore PREVENT"
          description="Calculado automaticamente (AHA, Khan et al. 2024) a partir dos dados clínicos abaixo — usado quando o paciente não se enquadra nas categorias de risco muito alto/extremo já avaliadas."
        />

        <SubHeading>Perfil lipídico e pressórico</SubHeading>
        <FieldGroup>
          {field('ct_mgdl')}
          {field('hdl_mgdl')}
          {field('sbp_mmhg')}
        </FieldGroup>

        <Separator />

        <SubHeading>Antropometria e função renal</SubHeading>
        <FieldGroup>
          {field('bmi')}
          {field('egfr')}
        </FieldGroup>

        <Separator />

        <SubHeading>Fatores clínicos</SubHeading>
        <FieldGroup>
          {field('fumante')}
          {field('hipertensao')}
          {field('antihtn_use')}
          {field('statin_use')}
        </FieldGroup>
      </Card>
    </div>
  );
}
