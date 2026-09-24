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
      {/* Única saída da calculadora de volta para a lista, inclusive dentro da
          Waid. Era um "←" de ~22 px de largura e sem nome para leitor de tela; agora
          o alvo tem a largura mínima de toque. */}
      <button
        type="button"
        onClick={onBack}
        aria-label="Voltar para a lista"
        style={{
          background: 'none', border: 'none', cursor: 'pointer', color: 'var(--pen2)', fontSize: 20, lineHeight: 1,
          minWidth: 'var(--toque-min)', marginLeft: -10, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        ←
      </button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 'var(--texto-apoio)', fontWeight: 700, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {title}
        </p>
        {subtitle && <p style={{ fontSize: 'var(--texto-micro)', color: 'var(--pen2)' }}>{subtitle}</p>}
      </div>
      {progress != null && (
        <div style={{ width: 80, height: 4, background: 'var(--line2)', borderRadius: 2, flexShrink: 0 }}>
          <div style={{ height: '100%', width: `${progress}%`, background: 'var(--petrol)', borderRadius: 2, transition: 'width 0.3s' }} />
        </div>
      )}
    </div>
  );
}
