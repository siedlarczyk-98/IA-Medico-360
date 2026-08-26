import { useRef, useState } from 'react';
import { useIsMobile } from '../hooks/useIsMobile';
import { tratarEnterParaEnviar, DICA_ENVIO } from '../lib/enterParaEnviar';

interface Props {
  onSend: (answers: string) => void;
}

export function ClarificationPrompt({ onSend }: Props) {
  const isMobile = useIsMobile();
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

  function submit() {
    if (!filled) return;
    onSend(value.trim());
    setValue('');
  }

  return (
    <div style={{ padding: '14px 0 22px', display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
      <div style={{
        width: 720, maxWidth: '92%',
        border: `1px solid ${filled ? 'var(--petrol)' : 'var(--mint)'}`,
        borderRadius: 14, background: '#fff',
        padding: 14, boxShadow: '0 4px 18px rgba(0,209,125,0.08)',
        transition: 'border-color 0.15s',
      }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--petrol)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)', display: 'inline-block' }} />
          Responda as perguntas acima para continuar
        </div>
        <textarea
          ref={ref}
          rows={3}
          value={value}
          onChange={handleInput}
          onKeyDown={e => tratarEnterParaEnviar(e, { isMobile, submit })}
          placeholder="Ex: Paciente masculino, 62 anos. Sintomas há 3 dias. HAS e DM2 controlados."
          style={{
            width: '100%', border: 'none', outline: 'none', resize: 'none',
            background: 'transparent', fontSize: 13.5, color: 'var(--ink)',
            lineHeight: 1.5, minHeight: 52,
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 8, marginTop: 8 }}>
          {!isMobile && <span style={{ fontSize: 10.5, color: 'var(--pen3)' }}>{DICA_ENVIO}</span>}
          <button
            onClick={submit}
            disabled={!filled}
            style={{
              height: 32, padding: '0 14px', borderRadius: 10, border: 'none',
              background: filled ? 'var(--green)' : 'var(--fill)',
              color: filled ? 'var(--ink)' : 'var(--pen3)',
              fontWeight: 700, fontSize: 12,
              display: 'flex', alignItems: 'center', gap: 6,
              transition: 'background 0.15s, color 0.15s',
            }}
          >
            Responder
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path d="M3 8 H13 M9 4 L13 8 L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
