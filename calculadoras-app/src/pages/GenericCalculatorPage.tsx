import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useCalculatorDetail } from '../hooks/useCalculatorDetail';
import { useExecuteCalculator } from '../hooks/useExecuteCalculator';
import { DynamicCalculatorForm } from '../components/DynamicCalculatorForm';
import { GenericResultPanel } from '../components/GenericResultPanel';
import { AiPrefillSection } from '../components/AiPrefillSection';
import { CalculatorTopbar } from '../components/CalculatorTopbar';
import { formSpecRegistry } from '../calculators/formSpecs';
import { validateRequired } from '../calculators/formHelpers';
import { ValidationError } from '../api/calculators';

export function GenericCalculatorPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const { data: calculator, isLoading } = useCalculatorDetail(slug ?? '');
  const { mutate: execute, isPending: executing, data: result, reset } = useExecuteCalculator(slug ?? '');

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [aiFilledKeys, setAiFilledKeys] = useState<Set<string>>(new Set());
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showErrors, setShowErrors] = useState(false);

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
      <CalculatorTopbar title={calculator.name} onBack={() => navigate('/')} />

      <div style={{ maxWidth: 780, margin: '0 auto', padding: '24px 16px 60px' }}>

        <AiPrefillSection slug={slug ?? ''} aiFilledCount={aiFilledKeys.size} onPrefill={handlePrefill} />

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
