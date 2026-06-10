import { useRef, useState } from 'react';
import { useIsMobile } from '../hooks/useIsMobile';

export type Effort = 'rápido' | 'detalhado';
export type OrchestratorMode = 'QUICK_SEARCH' | 'CLINICAL_REASONING' | 'PHARMA_CHECK' | 'PRODUCTIVITY';

const MODE_OPTIONS: { key: OrchestratorMode; label: string; shortLabel: string }[] = [
  { key: 'QUICK_SEARCH',       label: 'Busca Rápida',         shortLabel: 'Busca' },
  { key: 'CLINICAL_REASONING', label: 'Raciocínio Clínico',   shortLabel: 'Clínico' },
  { key: 'PHARMA_CHECK',       label: 'Farmacológico',        shortLabel: 'Farmácia' },
  { key: 'PRODUCTIVITY',       label: 'Produtividade',        shortLabel: 'Produt.' },
];

interface Props {
  onSend: (text: string, effort: Effort) => void;
  disabled?: boolean;
  placeholder?: string;
  mode?: OrchestratorMode;
  onModeChange?: (mode: OrchestratorMode) => void;
}

export function InputBar({ onSend, disabled, placeholder, mode = 'QUICK_SEARCH', onModeChange }: Props) {
  const isMobile = useIsMobile();
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
        {/* Seletor de modo — apenas no Orquestrador */}
        {onModeChange && <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {MODE_OPTIONS.map(opt => {
            const active = mode === opt.key;
            return (
              <button
                key={opt.key}
                onClick={() => onModeChange?.(opt.key)}
                title={opt.label}
                style={{
                  padding: '4px 11px', fontSize: 11, fontWeight: 600, borderRadius: 8,
                  border: `1px solid ${active ? 'var(--petrol)' : 'var(--line2)'}`,
                  background: active ? 'var(--petrol)' : 'transparent',
                  color: active ? '#fff' : 'var(--pen2)',
                  cursor: 'pointer',
                  transition: 'all 0.12s',
                  whiteSpace: 'nowrap',
                }}
              >
                {isMobile ? opt.shortLabel : opt.label}
              </button>
            );
          })}
        </div>}

        <textarea
          ref={ref}
          rows={2}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? 'Digite sua pergunta…'}
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
          {!isMobile && <span style={{ fontSize: 10.5, color: 'var(--pen3)' }}>⌘ + ⏎ enviar</span>}
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
