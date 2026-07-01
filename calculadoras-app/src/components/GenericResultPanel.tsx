import type { ExecuteResponse } from '../api/calculators';
import { DISCLAIMER } from '../tokens';

interface ScoreEntry {
  key: string;
  label: string;
  value: number;
  max?: number;
  interpretation?: string;
}

interface PrimaryEntry {
  label: string;
  value: number | string;
  unit?: string;
}

interface Alert {
  level: 'warning' | 'danger' | 'info';
  text: string;
}

interface GenericResult {
  primary?: PrimaryEntry;
  scores?: ScoreEntry[];
  alerts?: Alert[];
}

const ALERT_STYLE: Record<Alert['level'], { bg: string; border: string; color: string }> = {
  warning: { bg: '#fffbeb', border: '#fde68a', color: '#92400e' },
  danger:  { bg: 'var(--redBg)', border: '#f5b5ba', color: 'var(--redFg)' },
  info:    { bg: '#eff6ff', border: '#bfdbfe', color: '#1d4ed8' },
};

interface Props {
  result: ExecuteResponse;
}

export function GenericResultPanel({ result }: Props) {
  const r = (result.result ?? {}) as GenericResult;

  return (
    <div style={{ border: '2px solid var(--line)', borderRadius: 14, overflow: 'hidden' }}>
      <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20, background: '#fff' }}>

        {r.scores && r.scores.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
            {r.scores.map(s => (
              <div key={s.key} style={{ background: 'var(--fill2)', borderRadius: 10, padding: '16px 18px' }}>
                <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                  {s.label}
                </p>
                <p style={{ fontSize: 28, fontWeight: 800, color: 'var(--petrol)' }}>
                  {s.value}{s.max != null && <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--pen3)' }}> / {s.max}</span>}
                </p>
                {s.interpretation && (
                  <p style={{ fontSize: 13, color: 'var(--pen)', marginTop: 6 }}>{s.interpretation}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {!r.scores && r.primary && (
          <div style={{ background: 'var(--fill2)', borderRadius: 10, padding: '16px 18px' }}>
            <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
              {r.primary.label}
            </p>
            <p style={{ fontSize: 28, fontWeight: 800, color: 'var(--petrol)' }}>
              {r.primary.value}{r.primary.unit && <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--pen3)' }}> {r.primary.unit}</span>}
            </p>
          </div>
        )}

        {result.interpretation && (
          <p style={{ fontSize: 13, color: 'var(--pen)', lineHeight: 1.6 }}>{result.interpretation}</p>
        )}

        {r.alerts && r.alerts.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {r.alerts.map((a, i) => {
              const style = ALERT_STYLE[a.level] ?? ALERT_STYLE.warning;
              return (
                <div
                  key={i}
                  style={{
                    background: style.bg,
                    border: `1px solid ${style.border}`,
                    borderRadius: 10,
                    padding: '10px 14px',
                    fontSize: 13,
                    color: style.color,
                    lineHeight: 1.5,
                  }}
                >
                  {a.text}
                </div>
              );
            })}
          </div>
        )}

        <p style={{ fontSize: 11, color: 'var(--pen3)', borderTop: '1px solid var(--line2)', paddingTop: 12 }}>
          {DISCLAIMER}
        </p>
      </div>
    </div>
  );
}
