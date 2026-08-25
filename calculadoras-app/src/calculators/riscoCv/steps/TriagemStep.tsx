import { Card, CardHeader, CheckItem, Separator, SubHeading, Button } from '../ui';
import { IconShieldAlert, IconAlertTriangle, IconChevronRight } from '../icons';
import type { WizardStepProps } from './types';

/** Porta literal de `Step1VeryHigh.tsx` (app de referência). */

const EVENTOS_MAIORES = [
  { id: 'sca', label: 'Síndrome coronária aguda recente (últimos 12 meses)' },
  { id: 'iam', label: 'Histórico de infarto do miocárdio' },
  { id: 'avc', label: 'Histórico de AVC isquêmico' },
  { id: 'dap', label: 'Doença arterial periférica sintomática', description: 'Claudicação com ITB < 0,85, revascularização ou amputação prévia' },
];

const CONDICOES_ALTO_RISCO = [
  { id: 'idade65', label: 'Idade ≥ 65 anos' },
  { id: 'hf', label: 'Hipercolesterolemia familiar' },
  { id: 'crm-icp', label: 'Histórico de CRM ou ICP fora dos eventos maiores' },
  { id: 'dm', label: 'Diabetes Mellitus' },
  { id: 'has', label: 'Hipertensão arterial' },
  { id: 'drc', label: 'Doença renal crônica (TFGe 15–59 mL/min/1,73 m²)' },
  { id: 'tabagismo', label: 'Tabagismo atual' },
  { id: 'ldl-elevado', label: 'LDL-c persistentemente ≥ 100 mg/dL apesar de terapia máxima tolerada + ezetimiba' },
  { id: 'evento-agudo-2a', label: 'Evento agudo aterosclerótico com menos de 2 anos' },
];

export function TriagemStep({ state, onChange, onResult, onNext }: WizardStepProps) {
  const hasVeryHigh = state.dcvaManifesta || state.cac300;
  const hasAnySelection = hasVeryHigh || state.nenhumVeryHigh;
  const hasExtreme =
    state.eventosMaiores.length >= 2 ||
    (state.eventosMaiores.length >= 1 && state.condicoesAltoRisco.length >= 2);

  const toggleArray = (arr: string[], id: string) =>
    arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id];

  const handleSubmit = () => {
    if (state.dcvaManifesta && hasExtreme) {
      onResult('extreme');
    } else if (hasVeryHigh) {
      onResult('very-high');
    } else {
      onNext();
    }
  };

  const getButtonLabel = () => {
    if (state.dcvaManifesta && hasExtreme) return 'Ver Resultado (Extremo)';
    if (hasVeryHigh) return 'Ver Resultado (Muito Alto)';
    return 'Próximo';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader
          icon={<IconShieldAlert size={18} color="var(--risk-very-high)" />}
          iconColor="var(--risk-very-high)"
          title="Triagem de risco muito alto"
          description="Marque se o paciente apresenta alguma das condições abaixo."
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <CheckItem
            checked={state.dcvaManifesta}
            onChange={v => onChange({
              dcvaManifesta: v,
              cac300: false,
              nenhumVeryHigh: false,
              ...(!v ? { eventosMaiores: [], condicoesAltoRisco: [] } : {}),
            })}
            label="DCVA manifesta"
            description="Infarto, AVC, obstrução arterial ≥ 50%, revascularização prévia"
          />
          <CheckItem
            checked={state.cac300}
            onChange={v => onChange({
              cac300: v,
              dcvaManifesta: false,
              nenhumVeryHigh: false,
              eventosMaiores: [],
              condicoesAltoRisco: [],
            })}
            label="CAC > 300 UA"
            description="Escore de cálcio arterial coronariano superior a 300"
          />
          <Separator />
          <CheckItem
            checked={state.nenhumVeryHigh}
            onChange={v => onChange({
              nenhumVeryHigh: v,
              dcvaManifesta: false,
              cac300: false,
              eventosMaiores: [],
              condicoesAltoRisco: [],
            })}
            label="Nenhuma das condições acima"
          />
        </div>
      </Card>

      {state.dcvaManifesta && (
        <Card accentColor="var(--risk-extreme-border)">
          <CardHeader
            icon={<IconAlertTriangle size={18} color="var(--risk-extreme)" />}
            iconColor="var(--risk-extreme)"
            title="Verificar risco extremo"
            description="Extremo se ≥ 2 eventos maiores, ou 1 evento maior + ≥ 2 condições de alto risco."
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <SubHeading>Eventos cardiovasculares ateroscleróticos maiores</SubHeading>
            {EVENTOS_MAIORES.map(item => (
              <CheckItem
                key={item.id}
                checked={state.eventosMaiores.includes(item.id)}
                onChange={() => onChange({ eventosMaiores: toggleArray(state.eventosMaiores, item.id) })}
                label={item.label}
                description={item.description}
              />
            ))}
          </div>
          <Separator />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <SubHeading>Condições de alto risco</SubHeading>
            {CONDICOES_ALTO_RISCO.map(item => (
              <CheckItem
                key={item.id}
                checked={state.condicoesAltoRisco.includes(item.id)}
                onChange={() => onChange({ condicoesAltoRisco: toggleArray(state.condicoesAltoRisco, item.id) })}
                label={item.label}
              />
            ))}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button onClick={handleSubmit} disabled={!hasAnySelection}>
          {getButtonLabel()} <IconChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
