import { Card, CardHeader, Separator, SubHeading, Button, ToggleGroup, Label, InputField, CheckItem } from '../ui';
import { IconTarget, IconChevronRight, IconChevronLeft } from '../icons';
import { usePreventCalculator } from '../../../hooks/usePreventCalculator';
import type { RiskLevel } from '../riskTypes';
import type { WizardStepProps } from './types';

/**
 * Única exceção à porta 100% client-side: a referência (`Step4Prevent.tsx`) só
 * linka pro MDCalc e pede o score digitado manualmente. Aqui o escore PREVENT
 * (AHA, Khan et al. 2024) é calculado de verdade num endpoint dedicado
 * (`POST /prevent/calculate`, backend `app/calculators/formulas/cardiologia/
 * prevent.py`) — sem persistir execução/audit log, só para obter o número. O
 * branching a partir do score é idêntico ao da referência.
 */

interface Step4Props extends Omit<WizardStepProps, 'onResult'> {
  onResult: (level: RiskLevel, goToAggravants: boolean) => void;
}

export function PreventStep({ state, onChange, onResult, onBack }: Step4Props) {
  const { mutate: execute, isPending, error } = usePreventCalculator();

  const clinicalFieldsValid =
    state.idade !== '' && state.ctMgdl !== '' && state.hdlMgdl !== '' &&
    state.sbpMmhg !== '' && state.bmi !== '' && state.egfr !== '';

  const handleCalculate = () => {
    execute(
      {
        idade: Number(state.idade),
        sexo: state.sexo,
        ct_mgdl: Number(state.ctMgdl),
        hdl_mgdl: Number(state.hdlMgdl),
        sbp_mmhg: Number(state.sbpMmhg),
        bmi: Number(state.bmi),
        egfr: Number(state.egfr),
        diabetes: state.hasDM === true,
        fumante: state.fumante,
        antihtn_use: state.antihtnUse,
        statin_use: state.statinUse,
      },
      {
        onSuccess: data => {
          // -1 é um sentinela local: "já calculado, mas fora da faixa válida do
          // PREVENT" (idade < 30 ou > 79, ou IMC > 39,9) — o backend nesse caso
          // devolve todos os campos `null`. Distinto de `null` = "ainda não calculado".
          onChange({ preventScore: data.ascvd_10a ?? -1 });
        },
      }
    );
  };

  const score = state.preventScore;
  const calculated = score !== null;
  const unavailable = score === -1;
  const ldl = state.ldlMgdl;
  const scoreNum = calculated && !unavailable ? score : NaN;
  const ldlNum = ldl ? parseFloat(ldl) : NaN;
  const needsLdl = !unavailable && !isNaN(scoreNum) && scoreNum < 5;

  const getResultLevel = (): { level: RiskLevel; goToAggravants: boolean } | null => {
    // Fora da faixa válida do PREVENT (idade < 30/> 79 ou IMC > 39,9): segue direto
    // para os fatores agravantes, igual ao fallback do backend quando não há score.
    if (unavailable) return { level: 'low', goToAggravants: true };
    if (isNaN(scoreNum)) return null;
    if (scoreNum >= 20) return { level: 'high', goToAggravants: false };
    if (scoreNum >= 5) return { level: 'intermediate', goToAggravants: true };
    if (isNaN(ldlNum)) return null;
    if (ldlNum >= 190) return null;
    if (ldlNum >= 160) return { level: 'intermediate', goToAggravants: true };
    return { level: 'low', goToAggravants: true };
  };

  const result = getResultLevel();

  const clinicalInputChanged = () => onChange({ preventScore: null });

  const getButtonLabel = () => {
    if (!calculated) return 'Calcular PREVENT';
    if (!result) return 'Informe o LDL-c para continuar';
    if (!result.goToAggravants) return 'Ver Resultado (Alto)';
    return 'Avaliar Agravantes';
  };

  const handleSubmit = () => {
    if (!calculated) {
      handleCalculate();
      return;
    }
    if (!result) return;
    onResult(result.level, result.goToAggravants);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader
          icon={<IconTarget size={18} />}
          title="Escore PREVENT"
          description="Calculado automaticamente (AHA, Khan et al. 2024) a partir dos dados clínicos abaixo."
        />

        <SubHeading>Dados do paciente</SubHeading>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <Label>Sexo</Label>
            <ToggleGroup value={state.sexo} onChange={v => { onChange({ sexo: v }); clinicalInputChanged(); }} options={[{ value: 'M', label: 'Masculino' }, { value: 'F', label: 'Feminino' }]} />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-idade">Idade (anos)</Label>
            <InputField id="prevent-idade" type="number" min={30} max={79} value={state.idade} onChange={v => { onChange({ idade: v }); clinicalInputChanged(); }} />
          </div>
        </div>

        <Separator />

        <SubHeading>Perfil lipídico e pressórico</SubHeading>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-ct">Colesterol total (mg/dL)</Label>
            <InputField id="prevent-ct" type="number" value={state.ctMgdl} onChange={v => { onChange({ ctMgdl: v }); clinicalInputChanged(); }} />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-hdl">HDL-c (mg/dL)</Label>
            <InputField id="prevent-hdl" type="number" value={state.hdlMgdl} onChange={v => { onChange({ hdlMgdl: v }); clinicalInputChanged(); }} />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-sbp">PA sistólica (mmHg)</Label>
            <InputField id="prevent-sbp" type="number" value={state.sbpMmhg} onChange={v => { onChange({ sbpMmhg: v }); clinicalInputChanged(); }} />
          </div>
        </div>

        <Separator />

        <SubHeading>Antropometria e função renal</SubHeading>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-bmi">IMC (kg/m²)</Label>
            <InputField id="prevent-bmi" type="number" value={state.bmi} onChange={v => { onChange({ bmi: v }); clinicalInputChanged(); }} />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-egfr">TFGe (mL/min/1,73m²)</Label>
            <InputField id="prevent-egfr" type="number" value={state.egfr} onChange={v => { onChange({ egfr: v }); clinicalInputChanged(); }} />
          </div>
        </div>

        <Separator />

        <SubHeading>Fatores clínicos</SubHeading>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <CheckItem checked={state.fumante} onChange={v => { onChange({ fumante: v }); clinicalInputChanged(); }} label="Tabagismo atual" />
          <CheckItem checked={state.antihtnUse} onChange={v => { onChange({ antihtnUse: v }); clinicalInputChanged(); }} label="Uso de anti-hipertensivo" />
          <CheckItem checked={state.statinUse} onChange={v => { onChange({ statinUse: v }); clinicalInputChanged(); }} label="Uso de estatina" />
        </div>

        {calculated && (
          <div style={{ padding: '14px 16px', borderRadius: 10, background: 'var(--fill2)', textAlign: 'center' }}>
            {unavailable ? (
              <p style={{ fontSize: 13, color: 'var(--pen2)' }}>
                PREVENT não aplicável fora da faixa de 30–79 anos (ou IMC &gt; 39,9) — segue direto para os fatores agravantes.
              </p>
            ) : (
              <>
                <p style={{ fontSize: 12, color: 'var(--pen2)', marginBottom: 4 }}>Risco PREVENT em 10 anos</p>
                <p style={{ fontSize: 24, fontWeight: 800, color: 'var(--ink)' }}>{score}%</p>
              </>
            )}
          </div>
        )}

        {needsLdl && (
          <div>
            <Label htmlFor="prevent-ldl">LDL-c (mg/dL)</Label>
            <InputField id="prevent-ldl" type="number" placeholder="Ex: 145" value={state.ldlMgdl} onChange={v => onChange({ ldlMgdl: v })} />
            <p style={{ fontSize: 12, color: 'var(--pen2)', marginTop: 6 }}>
              Necessário para estratificação quando o risco PREVENT é inferior a 5%.
            </p>
          </div>
        )}

        {error && (
          <p style={{ fontSize: 12.5, color: 'var(--red)' }}>
            Não foi possível calcular o PREVENT. Confira os dados acima.
          </p>
        )}
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="outline" onClick={onBack}>
          <IconChevronLeft size={16} /> Voltar
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={(!calculated && !clinicalFieldsValid) || isPending || (calculated && !result)}
        >
          {isPending ? 'Calculando…' : getButtonLabel()} <IconChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
