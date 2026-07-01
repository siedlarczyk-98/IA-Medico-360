import { useNavigate } from 'react-router-dom';
import type { CalculatorListItem } from '../api/calculators';
import { getSpecialtyStyle } from '../lib/specialtyStyles';

const SLUG_TO_PATH: Record<string, string> = {
  risco_cv_sbc2025: '/calculadoras/risco-cv-sbc2025',
};

interface Props {
  calculator: CalculatorListItem;
  onToggleFavorite: (calculator: CalculatorListItem) => void;
}

export function CalculatorCard({ calculator, onToggleFavorite }: Props) {
  const navigate = useNavigate();
  const path = SLUG_TO_PATH[calculator.slug] ?? `/calculadoras/${calculator.slug}`;
  const specialty = getSpecialtyStyle(calculator.specialty_slug);
  const isFavorite = calculator.is_favorite;

  return (
    <button
      type="button"
      onClick={() => path && navigate(path)}
      disabled={!path}
      style={{
        position: 'relative',
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
        transition: 'box-shadow 0.15s, border-color 0.15s, transform 0.15s',
        width: '100%',
        height: '100%',
      }}
      onMouseEnter={e => {
        if (path) {
          (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 8px 24px rgba(1,71,81,0.12)';
          (e.currentTarget as HTMLButtonElement).style.borderColor = specialty.color;
          (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-2px)';
        }
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLButtonElement).style.boxShadow = 'none';
        (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--line)';
        (e.currentTarget as HTMLButtonElement).style.transform = 'none';
      }}
    >
      <span
        role="button"
        aria-label={isFavorite ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}
        onClick={e => {
          e.stopPropagation();
          onToggleFavorite(calculator);
        }}
        style={{
          position: 'absolute',
          top: 12,
          right: 12,
          width: 26,
          height: 26,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: 8,
          cursor: 'pointer',
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill={isFavorite ? '#f5a623' : 'none'}>
          <path d="M12 2.5l2.9 6.3 6.9.7-5.2 4.7 1.5 6.8L12 17.6l-6.1 3.4 1.5-6.8-5.2-4.7 6.9-.7L12 2.5z" stroke={isFavorite ? '#f5a623' : 'var(--pen3)'} strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
        <div style={{
          width: 36,
          height: 36,
          borderRadius: 10,
          background: specialty.bg,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          {specialty.icon}
        </div>
        <div style={{ flex: 1, minWidth: 0, paddingRight: 24 }}>
          <p style={{
            fontSize: 14,
            fontWeight: 700,
            color: 'var(--ink)',
            lineHeight: 1.3,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}>
            {calculator.name}
          </p>
          <span style={{
            display: 'inline-block',
            marginTop: 4,
            fontSize: 10,
            fontWeight: 700,
            color: specialty.color,
            background: specialty.bg,
            padding: '2px 8px',
            borderRadius: 999,
            textTransform: 'capitalize',
          }}>
            {specialty.label}
          </span>
        </div>
        {path && (
          <span style={{ fontSize: 16, color: 'var(--pen3)', flexShrink: 0, alignSelf: 'flex-start', marginTop: 2 }}>›</span>
        )}
      </div>
      {calculator.description && (
        <p style={{
          fontSize: 12,
          color: 'var(--pen2)',
          lineHeight: 1.5,
          marginLeft: 46,
          display: '-webkit-box',
          WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>
          {calculator.description}
        </p>
      )}
    </button>
  );
}
