import { useRef, useState } from 'react';

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function InputBar({ onSend, disabled, placeholder }: Props) {
  const [value, setValue] = useState('');
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
    onSend(value.trim());
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
          placeholder={placeholder ?? 'Pergunte algo clínico — o modo será roteado automaticamente.'}
          disabled={disabled}
          style={{
            width: '100%', border: 'none', outline: 'none', resize: 'none',
            background: 'transparent', fontSize: 13.5, color: 'var(--ink)',
            lineHeight: 1.5, minHeight: 36,
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
          <button style={{
            width: 28, height: 28, borderRadius: 8,
            border: '1px solid var(--line2)', background: '#fff',
            color: 'var(--pen2)', fontSize: 18, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
          }}>+</button>
          <Chip icon={<UploadIcon />}>Anexar exame</Chip>
          <Chip icon={<MicIcon />}>Ditar</Chip>
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

function Chip({ children, icon }: { children: React.ReactNode; icon: React.ReactNode }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 8px', fontSize: 10.5, fontWeight: 500,
      color: 'var(--pen)', background: 'var(--fill2)',
      border: '1px solid var(--line)', borderRadius: 999, cursor: 'pointer',
    }}>
      {icon}{children}
    </span>
  );
}

function UploadIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
      <path d="M8 3 V13 M5 6 L8 3 L11 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
      <rect x="6" y="2" width="4" height="9" rx="2" stroke="currentColor" strokeWidth="1.4" />
      <path d="M4 9 V10 Q4 12 8 12 Q12 12 12 10 V9 M8 12 V14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
