interface Props {
  title: string;
  subtitle?: string;
  onBack: () => void;
  /** 0–100. Quando informado, renderiza a barrinha de progresso à direita. */
  progress?: number;
}

export function CalculatorTopbar({ title, subtitle, onBack, progress }: Props) {
  return (
    <div style={{
      background: '#fff',
      borderBottom: '1px solid var(--line)',
      padding: '0 20px',
      height: 56,
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      position: 'sticky',
      top: 0,
      zIndex: 10,
    }}>
      <button
        type="button"
        onClick={onBack}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen2)', fontSize: 18, lineHeight: 1, padding: '4px 6px' }}
      >
        ←
      </button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {title}
        </p>
        {subtitle && <p style={{ fontSize: 11, color: 'var(--pen2)' }}>{subtitle}</p>}
      </div>
      {progress != null && (
        <div style={{ width: 80, height: 4, background: 'var(--line2)', borderRadius: 2, flexShrink: 0 }}>
          <div style={{ height: '100%', width: `${progress}%`, background: 'var(--petrol)', borderRadius: 2, transition: 'width 0.3s' }} />
        </div>
      )}
    </div>
  );
}
