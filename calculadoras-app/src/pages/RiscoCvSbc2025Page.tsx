import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCalculatorDetail } from '../hooks/useCalculatorDetail';
import { useExecuteCalculator } from '../hooks/useExecuteCalculator';
import { DynamicCalculatorForm } from '../components/DynamicCalculatorForm';
import { AiPrefillBox } from '../components/AiPrefillBox';
import { ResultPanel } from '../components/ResultPanel';
import { formSpecRegistry } from '../calculators/formSpecs';
import { ValidationError } from '../api/calculators';
import type { CalculatorField } from '../api/calculators';

// Side-effect: registers the formSpec for this slug.
import '../calculators/riscoCvSbc2025.formSpec';

const SLUG = 'risco_cv_sbc2025';

function buildVisibleInputs(
  values: Record<string, unknown>,
  fields: CalculatorField[],
  formSpec: import('../calculators/formSpecs').FormSpec | undefined
): Record<string, unknown> {
  if (!formSpec) {
    const out: Record<string, unknown> = {};
    for (const f of fields) {
      if (values[f.key] !== undefined) out[f.key] = values[f.key];
    }
    return out;
  }

  const visibleKeys = new Set<string>();
  const vals = values;

  function checkCond(cond: { field: string; equals?: unknown; notEquals?: unknown; includes?: unknown }): boolean {
    const v = vals[cond.field];
    if (cond.equals !== undefined)    return v === cond.equals;
    if (cond.notEquals !== undefined) return v !== cond.notEquals;
    if (cond.includes !== undefined)  return Array.isArray(v) && (v as unknown[]).includes(cond.includes);
    return true;
  }

  for (const section of formSpec.sections) {
    if (section.visibleWhen && !section.visibleWhen.every(checkCond)) continue;
    for (const f of section.fields) {
      if (!f.visibleWhen || f.visibleWhen.every(checkCond)) {
        visibleKeys.add(f.key);
      }
    }
  }

  const out: Record<string, unknown> = {};
  for (const key of visibleKeys) {
    if (values[key] !== undefined) out[key] = values[key];
  }
  return out;
}

function validateRequired(
  values: Record<string, unknown>,
  fields: CalculatorField[],
  visibleKeys: Set<string>
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const f of fields) {
    if (!f.required) continue;
    if (!visibleKeys.has(f.key)) continue;
    const v = values[f.key];
    if (v === undefined || v === null || v === '') {
      errors[f.key] = 'Campo obrigatório';
    }
  }
  return errors;
}

export function RiscoCvSbc2025Page() {
  const navigate = useNavigate();
  const { data: calculator, isLoading } = useCalculatorDetail(SLUG);
  const { mutate: execute, isPending: executing, data: result, reset } = useExecuteCalculator(SLUG);

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [aiFilledKeys, setAiFilledKeys] = useState<Set<string>>(new Set());
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showErrors, setShowErrors] = useState(false);
  const [showInfoModal, setShowInfoModal] = useState(true);
  const [showAiBox, setShowAiBox] = useState(false);

  const formSpec = formSpecRegistry[SLUG];

  function handleClear() {
    setValues({});
    setAiFilledKeys(new Set());
    setFieldErrors({});
    setShowErrors(false);
    reset();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function handleChange(key: string, value: unknown) {
    setValues(prev => ({ ...prev, [key]: value }));
    setAiFilledKeys(prev => { const n = new Set(prev); n.delete(key); return n; });
    setFieldErrors(prev => { const n = { ...prev }; delete n[key]; return n; });
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

    execute(inputs, {
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

      {/* Topbar */}
      <div style={{
        background: '#fff',
        borderBottom: '1px solid var(--line)',
        padding: '0 20px',
        height: 56,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <button
          type="button"
          onClick={() => navigate('/')}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen2)', fontSize: 18, lineHeight: 1, padding: '4px 6px' }}
        >
          ←
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {calculator.name}
          </p>
          <p style={{ fontSize: 11, color: 'var(--pen2)' }}>SBC 2025 · {filledRequired}/{requiredCount} obrigatórios</p>
        </div>
        {/* Progress bar */}
        <div style={{ width: 80, height: 4, background: 'var(--line2)', borderRadius: 2, flexShrink: 0 }}>
          <div style={{ height: '100%', width: `${progress}%`, background: 'var(--petrol)', borderRadius: 2, transition: 'width 0.3s' }} />
        </div>
      </div>

      <div style={{ maxWidth: 780, margin: '0 auto', padding: '24px 16px 60px' }}>

        {/* Botão IA Prefill */}
        <div style={{ marginBottom: 20 }}>
          {!showAiBox ? (
            <button
              type="button"
              onClick={() => setShowAiBox(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 16px',
                background: '#fff',
                border: '1px solid var(--line)',
                borderRadius: 10,
                fontSize: 13,
                fontWeight: 600,
                color: 'var(--pen)',
                cursor: 'pointer',
                transition: 'border-color 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--petrol)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--line)')}
            >
              <span style={{ fontSize: 14 }}>✦</span>
              Preencher a partir de uma evolução
            </button>
          ) : (
            <div>
              <AiPrefillBox slug={SLUG} onPrefill={(s, e) => { handlePrefill(s, e); setShowAiBox(false); }} />
              <button
                type="button"
                onClick={() => setShowAiBox(false)}
                style={{ marginTop: 8, fontSize: 12, color: 'var(--pen3)', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                ← Cancelar
              </button>
            </div>
          )}
        </div>

        {/* Aviso de campos IA preenchidos */}
        {aiFilledKeys.size > 0 && (
          <div style={{
            background: '#eff6ff',
            border: '1px solid #bfdbfe',
            borderRadius: 10,
            padding: '10px 14px',
            marginBottom: 16,
            fontSize: 12,
            color: '#1d4ed8',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <span>✦</span>
            <span>
              <strong>{aiFilledKeys.size} {aiFilledKeys.size === 1 ? 'campo preenchido' : 'campos preenchidos'} pela IA.</strong>
              {' '}Revise e confirme os valores antes de calcular.
            </span>
          </div>
        )}

        {/* Formulário */}
        <div style={{
          background: '#fff',
          border: '1px solid var(--line)',
          borderRadius: 14,
          padding: '24px 20px',
          marginBottom: 24,
        }}>
          <DynamicCalculatorForm
            fields={calculator.fields}
            formSpec={formSpec}
            values={values}
            onChange={handleChange}
            aiFilledKeys={aiFilledKeys}
            fieldErrors={fieldErrors}
            showErrors={showErrors}
          />
        </div>

        {/* Ações */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 28 }}>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={executing}
            style={{
              width: '100%',
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
            {executing ? 'Calculando…' : 'Calcular risco cardiovascular'}
          </button>

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
            <ResultPanel result={result} />
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
