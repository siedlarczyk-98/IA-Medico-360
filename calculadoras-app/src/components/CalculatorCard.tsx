import { useNavigate } from 'react-router-dom';
import type { CalculatorListItem } from '../api/calculators';

const SLUG_TO_PATH: Record<string, string> = {
  risco_cv_sbc2025: '/calculadoras/risco-cv-sbc2025',
};

interface Props {
  calculator: CalculatorListItem;
}

export function CalculatorCard({ calculator }: Props) {
  const navigate = useNavigate();
  const path = SLUG_TO_PATH[calculator.slug];

  return (
    <button
      type="button"
      onClick={() => path && navigate(path)}
      disabled={!path}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 8,
        padding: '20px 22px',
        background: '#fff',
        border: '1px solid var(--line)',
        borderRadius: 14,
        cursor: path ? 'pointer' : 'default',
        textAlign: 'left',
        transition: 'box-shadow 0.15s, border-color 0.15s',
        width: '100%',
      }}
      onMouseEnter={e => {
        if (path) {
          (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 18px rgba(1,71,81,0.1)';
          (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--petrol)';
        }
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLButtonElement).style.boxShadow = 'none';
        (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--line)';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
        <div style={{
          width: 36,
          height: 36,
          borderRadius: 10,
          background: 'var(--fill2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M9 12l2 2 4-4m-5-7H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V9l-5-5z" stroke="var(--petrol)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {calculator.name}
          </p>
          <p style={{ fontSize: 11, color: 'var(--pen2)', textTransform: 'capitalize' }}>
            {calculator.specialty_slug}
          </p>
        </div>
        {path && (
          <span style={{ fontSize: 16, color: 'var(--pen3)', flexShrink: 0 }}>›</span>
        )}
      </div>
      {calculator.description && (
        <p style={{ fontSize: 12, color: 'var(--pen2)', lineHeight: 1.5, marginLeft: 46 }}>
          {calculator.description}
        </p>
      )}
    </button>
  );
}
