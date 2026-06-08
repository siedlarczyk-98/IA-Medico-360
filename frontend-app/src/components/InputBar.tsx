import { useRef, useState } from 'react';

export type Effort = 'rápido' | 'detalhado';

interface Props {
  onSend: (text: string, effort: Effort) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function InputBar({ onSend, disabled, placeholder }: Props) {
  const [value, setValue] = useState('');
  const [effort, setEffort] = useState<Effort>('detalhado');
  const ref = useRef<HTMLTextAreaElement>(null);
  const filled = value.trim().length > 0;

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value);
    if (ref.current) {
      ref.current.style.height = 'auto';
      ref.current.style.height = ref.current.scrollHeight + 'px';
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit();
  }

  function submit() {
    if (!filled || disabled) return;
    onSend(value.trim(), effort);
    setValue('');
    if (ref.current) ref.current.style.height = 'auto';
  }

  return (
    <div style={{ padding: '14px 0 22px', display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
      <div style={{
        width: 720, maxWidth: '92%',
        border: `1px solid ${filled ? 'var(--petrol)' : 'var(--line)'}`,
        borderRadius: 14, background: '#fff',
        padding: 14, boxShadow: '0 4px 18px rgba(14,37,45,0.05)',
        transition: 'border-color 0.15s',
      }}>
        <textarea
          ref={ref}
          rows={2}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? 'Pergunte algo — o modo será roteado automaticamente.'}
          disabled={disabled}
          style={{
            width: '100%', border: 'none', outline: 'none', resize: 'none',
            background: 'transparent', fontSize: 13.5, color: 'var(--ink)',
            lineHeight: 1.5, minHeight: 36,
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
          {/* Segmented control de esforço */}
          <div style={{
            display: 'flex', borderRadius: 8, overflow: 'hidden',
            border: '1px solid var(--line2)', background: 'var(--fill)',
          }}>
            {(['rápido', 'detalhado'] as Effort[]).map(opt => (
              <button
                key={opt}
                onClick={() => setEffort(opt)}
                title={opt === 'rápido'
                  ? 'Resposta direta e objetiva — ideal para dúvidas rápidas do dia a dia'
                  : 'Resposta completa com raciocínio clínico detalhado — ideal para casos complexos'}
                style={{
                  padding: '3px 10px', fontSize: 10.5, fontWeight: 600, border: 'none',
                  background: effort === opt ? 'var(--petrol)' : 'transparent',
                  color: effort === opt ? '#fff' : 'var(--pen3)',
                  cursor: 'pointer', textTransform: 'capitalize',
                  transition: 'background 0.12s, color 0.12s',
                }}
              >
                {opt}
              </button>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 10.5, color: 'var(--pen3)' }}>⌘ + ⏎ enviar</span>
          <button
            onClick={submit}
            disabled={!filled || disabled}
            style={{
              height: 32, padding: '0 14px', borderRadius: 10, border: 'none',
              background: filled ? 'var(--green)' : 'var(--fill)',
              color: filled ? 'var(--ink)' : 'var(--pen3)',
              fontWeight: 700, fontSize: 12,
              display: 'flex', alignItems: 'center', gap: 6,
              transition: 'background 0.15s, color 0.15s',
            }}
          >
            Enviar
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path d="M3 8 H13 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

