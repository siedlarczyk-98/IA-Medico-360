import { useCallback, useState } from 'react';
import { useFormularioSalvo, usePreservarFormulario } from '@shared/embed/formulario';
import { donoDaSessao } from '../../lib/auth';
import { StepIndicator } from './StepIndicator';
import { TriagemStep } from './steps/TriagemStep';
import { DiabetesStep } from './steps/DiabetesStep';
import { AltoRiscoStep } from './steps/AltoRiscoStep';
import { PreventStep } from './steps/PreventStep';
import { AgravantesStep } from './steps/AgravantesStep';
import { RiscoCvResultDashboard } from './RiscoCvResultDashboard';
import { INITIAL_STATE, type RiskLevel, type WizardState } from './riskTypes';

const STEP_LABELS = ['Triagem', 'Diabetes', 'Alto Risco', 'PREVENT', 'Agravantes'];

/** O que volta depois de uma reentrada — ver `shared/embed/formulario.ts`. */
const CHAVE_FORMULARIO = 'risco-cv-sbc2025';
interface EstadoGuardado {
  step: number;
  state: WizardState;
  result: RiskLevel | null;
  preAggravantRisk: RiskLevel;
  completedSteps: number[];
}

/** Porta literal de `RiskCalculator.tsx` (app de referência) — orquestração 100% client-side. */
export function RiskCalculator() {
  // Quinze campos em cinco passos: é o formulário que mais custa redigitar quando
  // a sessão cai no passo do PREVENT (o único que chama o servidor). O guardado é
  // mesclado sobre o inicial porque pode ter vindo de uma versão anterior.
  const salvo = useFormularioSalvo<Partial<EstadoGuardado>>(CHAVE_FORMULARIO, donoDaSessao());
  const [step, setStep] = useState(salvo?.step ?? 0);
  const [state, setState] = useState<WizardState>({ ...INITIAL_STATE, ...salvo?.state });
  const [result, setResult] = useState<RiskLevel | null>(salvo?.result ?? null);
  const [preAggravantRisk, setPreAggravantRisk] = useState<RiskLevel>(salvo?.preAggravantRisk ?? 'low');
  const [completedSteps, setCompletedSteps] = useState<number[]>(salvo?.completedSteps ?? []);
  usePreservarFormulario(CHAVE_FORMULARIO, { step, state, result, preAggravantRisk, completedSteps });

  const updateState = useCallback((updates: Partial<WizardState>) => {
    setState(prev => ({ ...prev, ...updates }));
  }, []);

  const completeStep = (stepIndex: number) => {
    setCompletedSteps(prev => (prev.includes(stepIndex) ? prev : [...prev, stepIndex]));
  };

  const goToResult = (level: RiskLevel) => {
    completeStep(step);
    setResult(level);
  };

  const goToStep = (nextStep: number) => {
    completeStep(step);
    setStep(nextStep);
  };

  const handleStep4Result = (level: RiskLevel, goToAggravants: boolean) => {
    completeStep(3);
    if (!goToAggravants) {
      setResult(level);
    } else {
      setPreAggravantRisk(level);
      setStep(4);
    }
  };

  const restart = () => {
    setStep(0);
    setState({ ...INITIAL_STATE });
    setResult(null);
    setPreAggravantRisk('low');
    setCompletedSteps([]);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (result) {
    return <RiscoCvResultDashboard riskLevel={result} onRestart={restart} />;
  }

  return (
    <div>
      <StepIndicator steps={STEP_LABELS} currentStep={step} completedSteps={completedSteps} />

      {step === 0 && (
        <TriagemStep state={state} onChange={updateState} onResult={goToResult} onNext={() => goToStep(1)} />
      )}
      {step === 1 && (
        <DiabetesStep state={state} onChange={updateState} onResult={goToResult} onNext={() => goToStep(2)} onBack={() => setStep(0)} />
      )}
      {step === 2 && (
        <AltoRiscoStep state={state} onChange={updateState} onResult={goToResult} onNext={() => goToStep(3)} onBack={() => setStep(1)} />
      )}
      {step === 3 && (
        <PreventStep state={state} onChange={updateState} onResult={handleStep4Result} onNext={() => goToStep(4)} onBack={() => setStep(2)} />
      )}
      {step === 4 && (
        <AgravantesStep state={state} currentRisk={preAggravantRisk} onChange={updateState} onResult={goToResult} onBack={() => setStep(3)} />
      )}
    </div>
  );
}
