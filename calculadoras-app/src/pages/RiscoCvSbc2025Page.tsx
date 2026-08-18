import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCalculatorDetail } from '../hooks/useCalculatorDetail';
import { useExecuteCalculator } from '../hooks/useExecuteCalculator';
import { AiPrefillSection } from '../components/AiPrefillSection';
import { CalculatorTopbar } from '../components/CalculatorTopbar';
import { WizardStepper } from '../components/WizardStepper';
import { formSpecRegistry } from '../calculators/formSpecs';
import { buildVisibleInputs, checkVisibleCond, isVisibleSection, validateRequired } from '../calculators/formHelpers';
import { ValidationError } from '../api/calculators';
import { RiscoCvResultDashboard } from '../calculators/riscoCv/RiscoCvResultDashboard';
import { TriagemStep } from '../calculators/riscoCv/steps/TriagemStep';
import { DiabetesStep } from '../calculators/riscoCv/steps/DiabetesStep';
import { AltoRiscoStep } from '../calculators/riscoCv/steps/AltoRiscoStep';
import { PreventStep } from '../calculators/riscoCv/steps/PreventStep';
import { AgravantesStep } from '../calculators/riscoCv/steps/AgravantesStep';
import type { StepProps } from '../calculators/riscoCv/steps/types';

// Side-effect: registers the formSpec for this slug.
import '../calculators/riscoCvSbc2025.formSpec';

const SLUG = 'risco_cv_sbc2025';

const STEP_COMPONENTS: Record<string, (props: StepProps) => React.JSX.Element> = {
  triagem: TriagemStep,
  diabetes: DiabetesStep,
  alto_risco: AltoRiscoStep,
  prevent: PreventStep,
  agravantes: AgravantesStep,
};

// Passo máximo do algoritmo de estratificação (backend) que o wizard TENTA cobrir ao
// final de cada step — usado para decidir se um `passo_determinante` retornado pelo
// backend já pode encerrar o wizard (early-exit) neste ponto. É "best-effort": como a
// Triagem só coleta os campos centrais (sem duplicar dados de Diabetes/PREVENT), o
// early-exit pode ocasionalmente não fechar tão cedo quanto seria teoricamente possível
// (ex.: exigir o passo Diabetes para confirmar diabetes=true) — isso é intencional,
// priorizando uma Triagem enxuta sobre a precisão máxima do early-exit.
// Nota: 'prevent' fica em 4, não 5 — o Passo 5 do backend (PREVENT + fatores
// agravantes) SEMPRE retorna uma categoria assim que é alcançado, mas o resultado só é
// definitivo depois que os Agravantes também forem coletados (eles podem elevar BAIXO
// -> INTERMEDIARIO ou INTERMEDIARIO -> ALTO). Se tratássemos 'prevent' como cobrindo o
// Passo 5, o wizard nunca chegaria à tela de Agravantes.
const STEP_MAX_ALGO_STEP: Record<string, number> = {
  triagem: 1,
  diabetes: 3,
  alto_risco: 4,
  prevent: 4,
  agravantes: 5,
};

export function RiscoCvSbc2025Page() {
  const navigate = useNavigate();
  const { data: calculator, isLoading } = useCalculatorDetail(SLUG);
  const { mutate: execute, isPending: executing, data: result, reset } = useExecuteCalculator(SLUG);

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [aiFilledKeys, setAiFilledKeys] = useState<Set<string>>(new Set());
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showErrors, setShowErrors] = useState(false);
  const [showInfoModal, setShowInfoModal] = useState(true);
  const [stepIndex, setStepIndex] = useState(0);
  const [earlyExitAtStep, setEarlyExitAtStep] = useState<number | null>(null);

  const formSpec = formSpecRegistry[SLUG];
  const steps = formSpec?.steps;
  const isWizard = !!steps && steps.length > 0;
  const activeStep = isWizard ? steps![stepIndex] : undefined;
  const isLastStep = !isWizard || stepIndex === steps!.length - 1;

  function handleClear() {
    setValues({});
    setAiFilledKeys(new Set());
    setFieldErrors({});
    setShowErrors(false);
    setStepIndex(0);
    setEarlyExitAtStep(null);
    reset();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function keysForStep(stepKey: string): Set<string> {
    const keys = new Set<string>();
    if (!formSpec) return keys;
    for (const section of formSpec.sections) {
      if (section.step !== stepKey) continue;
      if (!isVisibleSection(section.visibleWhen, values)) continue;
      for (const f of section.fields) {
        if (!f.visibleWhen || f.visibleWhen.every(c => checkVisibleCond(c, values))) {
          keys.add(f.key);
        }
      }
    }
    return keys;
  }

  function advanceStep() {
    setShowErrors(false);
    setStepIndex(i => Math.min(i + 1, (steps?.length ?? 1) - 1));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function handleNext() {
    if (!calculator || !activeStep) return;
    const stepKeys = keysForStep(activeStep.key);
    const errors = validateRequired(values, calculator.fields, stepKeys);
    if (Object.keys(errors).length > 0) {
      setShowErrors(true);
      setFieldErrors(prev => ({ ...prev, ...errors }));
      const firstKey = Object.keys(errors)[0];
      document.querySelector(`[data-field="${firstKey}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    setShowErrors(false);

    const inputs = buildVisibleInputs(values, calculator.fields, formSpec);
    const maxAlgoStep = STEP_MAX_ALGO_STEP[activeStep.key];

    execute({ inputs, dryRun: true }, {
      onSuccess: data => {
        const passo = (data.result as { passo_determinante?: number | null }).passo_determinante;
        if (passo != null && maxAlgoStep != null && passo <= maxAlgoStep) {
          setEarlyExitAtStep(passo);
          setTimeout(() => {
            document.getElementById('result-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }, 100);
        } else {
          reset();
          advanceStep();
        }
      },
      onError: err => {
        if (err instanceof ValidationError) {
          setFieldErrors(prev => ({ ...prev, ...err.fieldErrors }));
        }
      },
    });
  }

  function handleBack() {
    setShowErrors(false);
    setEarlyExitAtStep(null);
    setStepIndex(i => Math.max(i - 1, 0));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function handleComplementMore() {
    reset();
    setEarlyExitAtStep(null);
    advanceStep();
  }

  function handleChange(key: string, value: unknown) {
    setValues(prev => ({ ...prev, [key]: value }));
    setAiFilledKeys(prev => { const n = new Set(prev); n.delete(key); return n; });
    setFieldErrors(prev => { const n = { ...prev }; delete n[key]; return n; });
    setEarlyExitAtStep(null);
    if (result) reset();
  }

  function handlePrefill(suggested: Record<string, unknown>, extracted: string[]) {
    setValues(prev => ({ ...prev, ...suggested }));
    setAiFilledKeys(new Set(extracted));
    reset();
  }

  function handleSubmit() {
    if (!calculator) return;
    setShowErrors(true);

    const inputs = buildVisibleInputs(values, calculator.fields, formSpec);

    const allVisibleKeys = new Set<string>();
    if (formSpec) {
      for (const section of formSpec.sections) {
        for (const f of section.fields) {
          allVisibleKeys.add(f.key);
        }
      }
    } else {
      calculator.fields.forEach(f => allVisibleKeys.add(f.key));
    }

    const clientErrors = validateRequired(values, calculator.fields, allVisibleKeys);
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      // Scroll to first error
      const firstKey = Object.keys(clientErrors)[0];
      document.querySelector(`[data-field="${firstKey}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    setFieldErrors({});

    execute({ inputs }, {
      onSuccess: () => {
        setFieldErrors({});
        setTimeout(() => {
          document.getElementById('result-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
      },
      onError: err => {
        if (err instanceof ValidationError) {
          setFieldErrors(err.fieldErrors);
        }
      },
    });
  }

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--fill2)' }}>
        <p style={{ fontSize: 14, color: 'var(--pen2)' }}>Carregando calculadora…</p>
      </div>
    );
  }

  if (!calculator) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ color: 'var(--red)' }}>Calculadora não encontrada.</p>
      </div>
    );
  }

  const requiredCount = calculator.fields.filter(f => f.required).length;
  const filledRequired = calculator.fields.filter(f => f.required && values[f.key] !== undefined).length;
  const progress = requiredCount > 0 ? Math.round((filledRequired / requiredCount) * 100) : 0;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--fill2)' }}>

      {/* Modal de boas-vindas — dados necessários */}
      {showInfoModal && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 100,
          background: 'rgba(14,37,45,0.45)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: 20,
        }}
          onClick={() => setShowInfoModal(false)}
        >
          <div
            style={{
              background: '#fff', borderRadius: 16,
              width: '100%', maxWidth: 480,
              padding: '28px 28px 24px',
              boxShadow: '0 12px 40px rgba(14,37,45,0.18)',
              display: 'flex', flexDirection: 'column', gap: 18,
            }}
            onClick={e => e.stopPropagation()}
          >
            <div>
              <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--petrol)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>
                O que você vai precisar
              </p>
              <h2 style={{ fontSize: 18, fontWeight: 800, color: 'var(--ink)', lineHeight: 1.3 }}>
                Risco Cardiovascular — SBC 2025
              </h2>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ background: 'var(--fill2)', borderRadius: 10, padding: '14px 16px' }}>
                <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--petrol)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                  Escore PREVENT (AHA)
                </p>
                <p style={{ fontSize: 12, color: 'var(--pen2)', marginBottom: 10, lineHeight: 1.5 }}>
                  Calculado quando o paciente tem <strong>30–79 anos</strong> e os dados abaixo estão disponíveis:
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px 8px' }}>
                  {[
                    ['Colesterol total', 'mg/dL'],
                    ['HDL-c', 'mg/dL'],
                    ['PA sistólica', 'mmHg'],
                    ['IMC', 'kg/m²'],
                    ['TFGe (eGFR)', 'mL/min/1,73m²'],
                  ].map(([label, unit]) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ color: 'var(--petrol)', fontSize: 9, flexShrink: 0 }}>●</span>
                      <span style={{ fontSize: 12, color: 'var(--pen)' }}>
                        {label} <span style={{ color: 'var(--pen3)' }}>({unit})</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ background: 'var(--fill2)', borderRadius: 10, padding: '14px 16px' }}>
                <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--petrol)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                  Fluxograma SBC 2025 — sempre calculado
                </p>
                <p style={{ fontSize: 12, color: 'var(--pen2)', lineHeight: 1.5 }}>
                  Avalia em sequência: evento CV prévio, doença aterosclerótica, diabetes e marcadores. Funciona mesmo sem os dados do PREVENT.
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowInfoModal(false)}
              style={{
                padding: '12px',
                background: 'var(--petrol)',
                color: '#fff',
                border: 'none',
                borderRadius: 10,
                fontSize: 14,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Entendido — começar preenchimento
            </button>
          </div>
        </div>
      )}

      <CalculatorTopbar
        title={calculator.name}
        subtitle={`SBC 2025 · ${filledRequired}/${requiredCount} obrigatórios`}
        progress={progress}
        onBack={() => navigate('/')}
      />

      {isWizard && steps && (
        <div style={{ background: '#fff', borderBottom: '1px solid var(--line)' }}>
          <div style={{ maxWidth: 780, margin: '0 auto' }}>
            <WizardStepper steps={steps} activeIndex={stepIndex} />
          </div>
        </div>
      )}

      <div style={{ maxWidth: 780, margin: '0 auto', padding: '24px 16px 60px' }}>

        <AiPrefillSection slug={SLUG} aiFilledCount={aiFilledKeys.size} onPrefill={handlePrefill} />

        {earlyExitAtStep != null ? (
          <div style={{
            background: 'var(--warning-bg)',
            border: '1px solid var(--warning-border)',
            borderRadius: 10,
            padding: '12px 16px',
            marginBottom: 16,
            fontSize: 13,
            color: 'var(--warning)',
          }}>
            Risco já determinado no Passo {earlyExitAtStep} do fluxograma — os dados dos passos seguintes não alterariam essa categoria. Você pode complementá-los se quiser registrar mais contexto clínico.
          </div>
        ) : (
          <>
            {/* Formulário */}
            <div style={{
              background: '#fff',
              border: '1px solid var(--line)',
              borderRadius: 14,
              padding: '24px 20px',
              marginBottom: 24,
            }}>
              {activeStep && (() => {
                const StepComponent = STEP_COMPONENTS[activeStep.key];
                return StepComponent ? (
                  <StepComponent
                    fields={calculator.fields}
                    formSpec={formSpec}
                    values={values}
                    onChange={handleChange}
                    aiFilledKeys={aiFilledKeys}
                    fieldErrors={fieldErrors}
                    showErrors={showErrors}
                  />
                ) : null;
              })()}
            </div>
          </>
        )}

        {/* Ações */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 28 }}>
          <div style={{ display: 'flex', gap: 10 }}>
            {isWizard && stepIndex > 0 && (
              <button
                type="button"
                onClick={handleBack}
                style={{
                  padding: '14px 18px',
                  background: 'none',
                  color: 'var(--pen)',
                  border: '1px solid var(--line)',
                  borderRadius: 10,
                  fontSize: 15,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                ← Voltar
              </button>
            )}
            {earlyExitAtStep != null ? (
              !isLastStep && (
                <button
                  type="button"
                  onClick={handleComplementMore}
                  style={{
                    flex: 1,
                    padding: '14px',
                    background: 'var(--petrol)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 10,
                    fontSize: 15,
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  Complementar mais dados →
                </button>
              )
            ) : (
              <button
                type="button"
                onClick={isLastStep ? handleSubmit : handleNext}
                disabled={executing}
                style={{
                  flex: 1,
                  padding: '14px',
                  background: executing ? 'var(--fill)' : 'var(--petrol)',
                  color: executing ? 'var(--pen3)' : '#fff',
                  border: 'none',
                  borderRadius: 10,
                  fontSize: 15,
                  fontWeight: 700,
                  cursor: executing ? 'not-allowed' : 'pointer',
                  transition: 'background 0.15s',
                }}
              >
                {isLastStep ? (executing ? 'Calculando…' : 'Calcular risco cardiovascular') : 'Próximo →'}
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={handleClear}
            style={{
              width: '100%',
              padding: '11px',
              background: 'none',
              color: 'var(--pen3)',
              border: '1px solid var(--line)',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'color 0.15s, border-color 0.15s',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.color = 'var(--red)';
              (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--red)';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.color = 'var(--pen3)';
              (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--line)';
            }}
          >
            Limpar formulário
          </button>
        </div>

        {/* Resultado */}
        {result && (
          <div id="result-panel">
            <RiscoCvResultDashboard result={result} />
          </div>
        )}
      </div>

      <style>{`
        input[type=number]::-webkit-inner-spin-button,
        input[type=number]::-webkit-outer-spin-button { opacity: 0.5; }
      `}</style>
    </div>
  );
}
