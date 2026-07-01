import { useState } from 'react';
import { AiPrefillBox } from './AiPrefillBox';

interface Props {
  slug: string;
  aiFilledCount: number;
  onPrefill: (suggested: Record<string, unknown>, extracted: string[]) => void;
}

/** Botão "Preencher a partir de uma evolução" + caixa de extração via IA + aviso de campos preenchidos. */
export function AiPrefillSection({ slug, aiFilledCount, onPrefill }: Props) {
  const [showAiBox, setShowAiBox] = useState(false);

  return (
    <>
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
            <AiPrefillBox slug={slug} onPrefill={(s, e) => { onPrefill(s, e); setShowAiBox(false); }} />
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

      {aiFilledCount > 0 && (
        <div style={{
          background: 'var(--info-bg)',
          border: '1px solid var(--info-border)',
          borderRadius: 10,
          padding: '10px 14px',
          marginBottom: 16,
          fontSize: 12,
          color: 'var(--info)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          <span>✦</span>
          <span>
            <strong>{aiFilledCount} {aiFilledCount === 1 ? 'campo preenchido' : 'campos preenchidos'} pela IA.</strong>
            {' '}Revise e confirme os valores antes de calcular.
          </span>
        </div>
      )}
    </>
  );
}
