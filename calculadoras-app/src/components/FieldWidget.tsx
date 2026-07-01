import type { CalculatorField } from '../api/calculators';

interface Props {
  field: CalculatorField;
  value: unknown;
  onChange: (value: unknown) => void;
  aiPrefilled?: boolean;
  error?: string;
  showError?: boolean;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  border: '1px solid var(--line)',
  borderRadius: 8,
  fontSize: 14,
  color: 'var(--ink)',
  outline: 'none',
  background: '#fff',
  boxSizing: 'border-box',
};

const inputErrorStyle: React.CSSProperties = {
  ...inputStyle,
  borderColor: 'var(--red)',
};

export function FieldWidget({ field, value, onChange, aiPrefilled, error, showError }: Props) {
  const hasError = showError && !!error;
  const base = hasError ? inputErrorStyle : inputStyle;

  const labelNode = (
    <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--pen)', letterSpacing: '0.03em', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
      {field.label}
      {field.unit && <span style={{ fontWeight: 400, color: 'var(--pen2)' }}>({field.unit})</span>}
      {field.required && <span style={{ color: 'var(--red)', fontWeight: 700 }}>*</span>}
      {aiPrefilled && (
        <span style={{
          fontSize: 10,
          fontWeight: 600,
          background: '#eff6ff',
          color: '#1d4ed8',
          border: '1px solid #bfdbfe',
          borderRadius: 4,
          padding: '1px 5px',
          letterSpacing: '0.02em',
        }}>
          IA
        </span>
      )}
    </label>
  );

  if (field.field_type === 'boolean') {
    const boolVal = value as boolean | undefined;
    return (
      <div data-field={field.key}>
        {labelNode}
        <div style={{ display: 'flex', gap: 6 }}>
          {(['true', 'false'] as const).map(opt => {
            const isOpt = opt === 'true';
            const active = boolVal === isOpt;
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onChange(isOpt)}
                style={{
                  flex: 1,
                  padding: '8px 12px',
                  borderRadius: 8,
                  border: active
                    ? `2px solid var(--petrol)`
                    : hasError && boolVal === undefined
                      ? '1px solid var(--red)'
                      : '1px solid var(--line)',
                  background: active ? 'var(--petrol)' : '#fff',
                  color: active ? '#fff' : 'var(--pen)',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.12s',
                }}
              >
                {isOpt ? 'Sim' : 'Não'}
              </button>
            );
          })}
        </div>
        {hasError && <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 3 }}>{error}</p>}
      </div>
    );
  }

  if (field.field_type === 'select') {
    return (
      <div data-field={field.key}>
        {labelNode}
        <select
          value={value != null ? String(value) : ''}
          onChange={e => onChange(e.target.value || undefined)}
          style={{ ...base, appearance: 'auto' }}
        >
          <option value="">Selecionar…</option>
          {(field.options ?? []).map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {hasError && <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 3 }}>{error}</p>}
      </div>
    );
  }

  if (field.field_type === 'multiselect') {
    const arrVal = (value as string[] | undefined) ?? [];
    return (
      <div data-field={field.key}>
        {labelNode}
        <div style={{
          border: hasError ? '1px solid var(--red)' : '1px solid var(--line)',
          borderRadius: 8,
          padding: '8px 10px',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          background: '#fff',
        }}>
          {(field.options ?? []).map(o => {
            const checked = arrVal.includes(o.value);
            return (
              <label key={o.value} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--pen)', lineHeight: 1.4 }}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={e => {
                    const next = e.target.checked
                      ? [...arrVal, o.value]
                      : arrVal.filter(v => v !== o.value);
                    onChange(next.length > 0 ? next : undefined);
                  }}
                  style={{ marginTop: 2, flexShrink: 0 }}
                />
                {o.label}
              </label>
            );
          })}
        </div>
        {hasError && <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 3 }}>{error}</p>}
      </div>
    );
  }

  if (field.field_type === 'number' || field.field_type === 'integer') {
    return (
      <div data-field={field.key}>
        {labelNode}
        <input
          type="number"
          step={field.field_type === 'integer' ? '1' : 'any'}
          min={field.min_value ?? undefined}
          max={field.max_value ?? undefined}
          value={value != null ? String(value) : ''}
          onChange={e => {
            const v = e.target.value;
            if (v === '') { onChange(undefined); return; }
            onChange(field.field_type === 'integer' ? parseInt(v, 10) : parseFloat(v));
          }}
          style={base}
        />
        {hasError && <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 3 }}>{error}</p>}
      </div>
    );
  }

  return (
    <div data-field={field.key}>
      {labelNode}
      <input
        type="text"
        value={value != null ? String(value) : ''}
        onChange={e => onChange(e.target.value || undefined)}
        style={base}
      />
      {hasError && <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 3 }}>{error}</p>}
    </div>
  );
}
