import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useCalculatorDetail } from '../hooks/useCalculatorDetail';
import { useExecuteCalculator } from '../hooks/useExecuteCalculator';
import { DynamicCalculatorForm } from '../components/DynamicCalculatorForm';
import { GenericResultPanel } from '../components/GenericResultPanel';
import { AiPrefillBox } from '../components/AiPrefillBox';
import { formSpecRegistry } from '../calculators/formSpecs';
import { ValidationError } from '../api/calculators';
import type { CalculatorField } from '../api/calculators';

function validateRequired(
  values: Record<string, unknown>,
  fields: CalculatorField[]
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const f of fields) {
    if (!f.required) continue;
    const v = values[f.key];
    if (v === undefined || v === null || v === '') {
      errors[f.key] = 'Campo obrigatório';
    }
  }
  return errors;
}

export function GenericCalculatorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const { data: calculator, isLoading } = useCalculatorDetail(slug ?? '');
  const { mutate: execute, isPending: executing, data: result, reset } = useExecuteCalculator(slug ?? '');

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [aiFilledKeys, setAiFilledKeys] = useState<Set<string>>(new Set());
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showErrors, setShowErrors] = useState(false);
  const [showAiBox, setShowAiBox] = useState(false);

  const formSpec = slug ? formSpecRegistry[slug] : undefined;

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

  function handleClear() {
    setValues({});
    setAiFilledKeys(new Set());
    setFieldErrors({});
    setShowErrors(false);
    reset();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function handleSubmit() {
    if (!calculator) return;
    setShowErrors(true);

    const errors = validateRequired(values, calculator.fields);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      const firstKey = Object.keys(errors)[0];
      document.querySelector(`[data-field="${firstKey}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    setFieldErrors({});
    execute({ inputs: values }, {
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

  return (
    <div style={{ minHeight: '100vh', background: 'var(--fill2)' }}>
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
        <p style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {calculator.name}
        </p>
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
              <AiPrefillBox slug={slug ?? ''} onPrefill={(s, e) => { handlePrefill(s, e); setShowAiBox(false); }} />
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

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 28 }}>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={executing}
            style={{
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
            {executing ? 'Calculando…' : 'Calcular'}
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
            }}
          >
            Limpar formulário
          </button>
        </div>

        {result && (
          <div id="result-panel">
            <GenericResultPanel result={result} />
          </div>
        )}
      </div>
    </div>
  );
}
