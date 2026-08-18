import { FieldWidget } from '../../../components/FieldWidget';
import { Card, CardHeader, FieldGroup, Separator } from '../ui';
import { IconUser, IconAlertTriangle } from '../icons';
import { makeFieldVisibility, pickField } from '../visibility';
import type { StepProps } from './types';

export function TriagemStep({ fields, formSpec, values, onChange, aiFilledKeys, fieldErrors, showErrors }: StepProps) {
  const isVisible = makeFieldVisibility(formSpec, 'triagem', values);

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
        <CardHeader icon={<IconUser size={18} />} title="Dados do paciente" />
        <FieldGroup>
          {field('idade')}
          {field('sexo')}
        </FieldGroup>
      </Card>

      <Card>
        <CardHeader
          icon={<IconAlertTriangle size={18} color="var(--red)" />}
          iconColor="var(--red)"
          title="Evento cardiovascular prévio"
          description="Evento aterosclerótico manifesto prévio (infarto, AVC, obstrução arterial ≥ 50%, revascularização)."
        />
        <FieldGroup>
          {field('evento_cv_previo')}
          {field('tipos_evento_cv')}
        </FieldGroup>
      </Card>

      <Card>
        <CardHeader
          title="Critério de risco extremo"
          description="Usado em conjunto com os eventos acima para identificar risco extremo (múltiplos eventos maiores, ou 1 evento + ≥ 2 condições abaixo)."
        />
        <Separator />
        <FieldGroup>
          {field('cirurgia_revasc_previa_fora_evento')}
          {field('ldl_persistente_ge100_max_tto')}
          {field('evento_agudo_lt2anos')}
        </FieldGroup>
      </Card>
    </div>
  );
}
