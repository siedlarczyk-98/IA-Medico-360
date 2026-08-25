import { useState } from 'react';
import { Card, CardHeader, CheckItem, Separator, SubHeading, Button, ToggleGroup, Label, InputField, Dialog } from '../ui';
import { IconStethoscope, IconUser, IconChevronRight, IconChevronLeft } from '../icons';
import type { WizardStepProps } from './types';
import type { RiskLevel } from '../riskTypes';
import tabelaDrdRisco from '../../../assets/tabela-drd-risco.png';

/** Porta literal de `Step2Diabetes.tsx` (app de referência). */

const EMAR_1_ITEMS = [
  { id: 'emar1-3ear', label: 'Três ou mais EAR' },
  { id: 'emar1-dm1-20a', label: 'DM1 com duração maior que 20 anos, diagnosticado após os 18 anos de idade' },
  { id: 'emar1-estenose50', label: 'Estenose maior do que 50% em qualquer território vascular' },
  { id: 'emar1-renal', label: 'EMAR renal (classificar)', linkLabel: 'ver tabela' },
  { id: 'emar1-hc-grave', label: 'Hipercolesterolemia grave: CT > 310 mg/dL ou LDL-c > 190 mg/dL' },
  { id: 'emar1-nac', label: 'Neuropatia autonômica cardiovascular instalada: dois TAC alterados para NAC' },
  { id: 'emar1-retino', label: 'Retinopatia diabética não proliferativa moderada-severa ou severa, proliferativa, ou evidência de progressão' },
];

const EMAR_2_ITEMS = [
  { id: 'emar2-sca', label: 'Síndrome coronariana aguda: IAM ou angina instável' },
  { id: 'emar2-iam-antigo', label: 'IAM antigo ou angina estável' },
  { id: 'emar2-avc', label: 'AVC aterotrombótico ou AIT' },
  { id: 'emar2-revasc', label: 'Revascularização coronariana, carotídea, renal ou periférica' },
  { id: 'emar2-ivp', label: 'Insuficiência vascular periférica ou amputação de membros' },
];

const EAR_ITEMS = [
  { id: 'ear-dm2-10a', label: 'DM2 há mais de 10 anos' },
  { id: 'ear-hf-dac', label: 'História familiar de doença arterial coronária prematura' },
  { id: 'ear-sm-idf', label: 'Síndrome metabólica definida pelo IDF' },
  { id: 'ear-has', label: 'Hipertensão arterial tratada ou não' },
  { id: 'ear-tabagismo', label: 'Tabagismo ativo' },
  { id: 'ear-nac-incipiente', label: 'Neuropatia autonômica cardiovascular incipiente' },
  { id: 'ear-retino-leve', label: 'Retinopatia diabética não proliferativa leve' },
  { id: 'ear-cac-10-300', label: 'Escore de cálcio coronário entre 10–300 UA' },
  { id: 'ear-placa-carotida', label: 'Placa carótida < 50%' },
  { id: 'ear-angiotc', label: 'Angiotomografia coronária com placa aterosclerótica < 50%' },
  { id: 'ear-aneurisma', label: 'Aneurisma da aorta abdominal' },
  { id: 'ear-drc-alto', label: 'Doença renal estratificada como risco alto', linkLabel: 'ver tabela' },
];

export function DiabetesStep({ state, onChange, onResult, onNext, onBack }: WizardStepProps) {
  const [showRenalDialog, setShowRenalDialog] = useState(false);

  const toggleArray = (arr: string[], id: string) =>
    arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id];

  const age = parseInt(state.dmAge, 10);
  const isOlderThreshold = state.dmSex === 'M' ? age >= 50 : age >= 56;
  const hasEmar = state.dm2EmarItems.length >= 1;
  const earCount = state.dm2EarItems.length;
  const dm2IsVeryHigh = hasEmar || earCount >= 3;

  const getDmRisk = (): RiskLevel | null => {
    if (dm2IsVeryHigh) return 'very-high';
    if (earCount >= 1 && earCount <= 2 && !hasEmar) return 'high';
    if (!isNaN(age) && isOlderThreshold && earCount === 0 && !hasEmar) return 'high';
    if (!isNaN(age) && !isOlderThreshold && earCount === 0 && !hasEmar) return 'intermediate';
    return null;
  };

  const dmRisk = state.hasDM === true ? getDmRisk() : null;
  const ageValid = state.dmAge !== '' && !isNaN(age);

  const handleSubmit = () => {
    if (state.hasDM === false) {
      onNext();
      return;
    }
    if (state.hasDM === true && dmRisk) {
      onResult(dmRisk);
    }
  };

  const getButtonLabel = () => {
    if (state.hasDM === false) return 'Próximo';
    if (dmRisk === 'very-high') return 'Ver Resultado (Muito Alto)';
    if (dmRisk === 'high') return 'Ver Resultado (Alto)';
    if (dmRisk === 'intermediate') return 'Ver Resultado (Intermediário)';
    return 'Ver Resultado';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader
          icon={<IconStethoscope size={18} />}
          title="Diabetes mellitus"
          description="O paciente possui diagnóstico de Diabetes Mellitus?"
        />
        <ToggleGroup
          value={state.hasDM === null ? null : state.hasDM ? 'sim' : 'nao'}
          onChange={v => onChange(v === 'sim' ? { hasDM: true } : { hasDM: false, dm2EmarItems: [], dm2EarItems: [] })}
          options={[{ value: 'sim', label: 'Sim' }, { value: 'nao', label: 'Não' }]}
        />
      </Card>

      {state.hasDM === true && (
        <Card>
          <CardHeader icon={<IconUser size={18} />} title="Dados do paciente" description="Informe a idade e o sexo para a estratificação de risco." />
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ flex: 1 }}>
              <Label htmlFor="dm-age">Idade (anos)</Label>
              <InputField id="dm-age" type="number" min={1} max={120} placeholder="Ex: 55" value={state.dmAge} onChange={v => onChange({ dmAge: v })} />
            </div>
            <div style={{ flex: 1 }}>
              <Label>Sexo</Label>
              <ToggleGroup
                value={state.dmSex}
                onChange={v => onChange({ dmSex: v })}
                options={[{ value: 'M', label: 'Masculino' }, { value: 'F', label: 'Feminino' }]}
              />
            </div>
          </div>
        </Card>
      )}

      {state.hasDM === true && (
        <Card accentColor="var(--risk-very-high-border)">
          <CardHeader
            icon={<IconStethoscope size={18} color="var(--risk-very-high)" />}
            iconColor="var(--risk-very-high)"
            title="Estratificadores — DM"
            description="Muito alto risco se ≥ 1 EMAR ou ≥ 3 EAR selecionados."
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <SubHeading>EMAR-1 — Sem evento CV prévio</SubHeading>
            <p style={{ fontSize: 12, color: 'var(--pen2)', marginTop: -6 }}>
              Estratificadores de Muito Alto Risco sem evento cardiovascular aterosclerótico manifesto prévio.
            </p>
            {EMAR_1_ITEMS.map(item => (
              <CheckItem
                key={item.id}
                checked={state.dm2EmarItems.includes(item.id)}
                onChange={() => onChange({ dm2EmarItems: toggleArray(state.dm2EmarItems, item.id) })}
                label={
                  item.linkLabel ? (
                    <>
                      {item.label}{' '}
                      <button
                        type="button"
                        onClick={e => { e.preventDefault(); e.stopPropagation(); setShowRenalDialog(true); }}
                        style={{ marginLeft: 4, fontSize: 12, color: 'var(--petrol)', textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer' }}
                      >
                        {item.linkLabel}
                      </button>
                    </>
                  ) : item.label
                }
              />
            ))}
          </div>

          <Separator />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <SubHeading>EMAR-2 — Com evento CV prévio</SubHeading>
            <p style={{ fontSize: 12, color: 'var(--pen2)', marginTop: -6 }}>
              Evento cardiovascular aterosclerótico manifesto prévio.
            </p>
            {EMAR_2_ITEMS.map(item => (
              <CheckItem
                key={item.id}
                checked={state.dm2EmarItems.includes(item.id)}
                onChange={() => onChange({ dm2EmarItems: toggleArray(state.dm2EmarItems, item.id) })}
                label={item.label}
              />
            ))}
          </div>

          <Separator />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <SubHeading hint={`Selecionados: ${state.dm2EarItems.length}/3`}>EAR — Estratificadores de Alto Risco</SubHeading>
            <p style={{ fontSize: 12, color: 'var(--pen2)', marginTop: -6 }}>
              ≥ 3 itens selecionados = Muito Alto Risco.
            </p>
            {EAR_ITEMS.map(item => (
              <CheckItem
                key={item.id}
                checked={state.dm2EarItems.includes(item.id)}
                onChange={() => onChange({ dm2EarItems: toggleArray(state.dm2EarItems, item.id) })}
                label={
                  item.linkLabel ? (
                    <>
                      {item.label}{' '}
                      <button
                        type="button"
                        onClick={e => { e.preventDefault(); e.stopPropagation(); setShowRenalDialog(true); }}
                        style={{ marginLeft: 4, fontSize: 12, color: 'var(--petrol)', textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer' }}
                      >
                        {item.linkLabel}
                      </button>
                    </>
                  ) : item.label
                }
              />
            ))}
          </div>
        </Card>
      )}

      <Dialog
        open={showRenalDialog}
        onClose={() => setShowRenalDialog(false)}
        title="Doença Renal Diabética — Estratificação de Risco"
        description="Tabela de referência para classificação de risco renal (Tabela 4.7)."
      >
        <img src={tabelaDrdRisco} alt="Tabela 4.7 — Estratificação de risco da doença renal diabética" style={{ maxWidth: '100%', borderRadius: 10, border: '1px solid var(--line)' }} />
      </Dialog>

      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="outline" onClick={onBack}>
          <IconChevronLeft size={16} /> Voltar
        </Button>
        <Button onClick={handleSubmit} disabled={state.hasDM === null || (state.hasDM === true && (!ageValid || !dmRisk))}>
          {getButtonLabel()} <IconChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
