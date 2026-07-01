import { useState } from 'react';
import { useExtractFields } from '../hooks/useExtractFields';

interface Props {
  slug: string;
  onPrefill: (suggested: Record<string, unknown>, extracted: string[]) => void;
}

export function AiPrefillBox({ slug, onPrefill }: Props) {
  const [text, setText] = useState('');
  const { mutate, isPending, error } = useExtractFields(slug);

  function handleSubmit() {
    if (!text.trim()) return;
    mutate(text, {
      onSuccess: res => {
        onPrefill(res.suggested_inputs, res.fields_extracted);
        setText('');
      },
    });
  }

  return (
    <div style={{
      border: '1px solid var(--info-border)',
      borderRadius: 12,
      background: 'var(--info-bg)',
      padding: '16px 18px',
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--info)' }}>✦ Preencher com IA</span>
        <span style={{ fontSize: 12, color: 'var(--info)' }}>Cole um trecho da evolução e a IA extrai os campos</span>
      </div>

      <textarea
        placeholder="Ex.: Paciente masculino, 58 anos, DM2 há 12 anos, HAS, LDL 110 mg/dL, HDL 38 mg/dL, CT 210 mg/dL, PA 148/90 mmHg, IMC 29, TFGe 72, tabagista, em uso de metformina e losartana…"
        value={text}
        onChange={e => setText(e.target.value)}
        rows={4}
        style={{
          width: '100%',
          padding: '10px 12px',
          border: '1px solid var(--info-border)',
          borderRadius: 8,
          fontSize: 13,
          color: 'var(--ink)',
          lineHeight: 1.5,
          outline: 'none',
          background: '#fff',
          resize: 'vertical',
          boxSizing: 'border-box',
        }}
      />

      {error && (
        <p style={{ fontSize: 12, color: 'var(--red)', background: 'var(--red-bg)', padding: '6px 10px', borderRadius: 6 }}>
          {error instanceof Error ? error.message : 'Erro ao extrair campos'}
        </p>
      )}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={isPending || !text.trim()}
        style={{
          alignSelf: 'flex-start',
          padding: '9px 18px',
          background: isPending || !text.trim() ? 'var(--fill)' : 'var(--info)',
          color: isPending || !text.trim() ? 'var(--pen3)' : '#fff',
          border: 'none',
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 600,
          cursor: isPending || !text.trim() ? 'not-allowed' : 'pointer',
          transition: 'background 0.15s',
        }}
      >
        {isPending ? 'Extraindo…' : 'Preencher campos'}
      </button>
    </div>
  );
}
