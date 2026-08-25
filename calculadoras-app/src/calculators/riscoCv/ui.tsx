import type { ReactNode } from 'react';

interface ButtonProps {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'default' | 'outline';
  disabled?: boolean;
  type?: 'button' | 'submit';
  style?: React.CSSProperties;
}

export function Button({ children, onClick, variant = 'default', disabled, type = 'button', style }: ButtonProps) {
  const isDefault = variant === 'default';
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        padding: '11px 18px',
        borderRadius: 10,
        fontSize: 14,
        fontWeight: 700,
        border: isDefault ? 'none' : '1px solid var(--line)',
        background: disabled ? 'var(--fill)' : isDefault ? 'var(--petrol)' : '#fff',
        color: disabled ? 'var(--pen3)' : isDefault ? '#fff' : 'var(--pen)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background 0.15s, color 0.15s, border-color 0.15s',
        ...style,
      }}
    >
      {children}
    </button>
  );
}

interface ToggleGroupOption<T extends string> {
  value: T;
  label: string;
}

interface ToggleGroupProps<T extends string> {
  value: T | null;
  onChange: (v: T) => void;
  options: ToggleGroupOption<T>[];
}

/** Par (ou trio) de botões estilo Sim/Não, para campos booleanos/enum simples. */
export function ToggleGroup<T extends string>({ value, onChange, options }: ToggleGroupProps<T>) {
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      {options.map(opt => (
        <Button
          key={opt.value}
          variant={value === opt.value ? 'default' : 'outline'}
          onClick={() => onChange(opt.value)}
          style={{ flex: 1 }}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  );
}

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} style={{ fontSize: 12, fontWeight: 600, color: 'var(--pen)', letterSpacing: '0.03em', display: 'block', marginBottom: 5 }}>
      {children}
    </label>
  );
}

interface InputFieldProps {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
}

export function InputField({ id, value, onChange, type = 'text', placeholder, min, max, step }: InputFieldProps) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      placeholder={placeholder}
      min={min}
      max={max}
      step={step}
      onChange={e => onChange(e.target.value)}
      style={{
        width: '100%',
        padding: '8px 10px',
        border: '1px solid var(--line)',
        borderRadius: 8,
        fontSize: 14,
        color: 'var(--ink)',
        outline: 'none',
        background: '#fff',
        boxSizing: 'border-box',
      }}
    />
  );
}

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
}

/** Modal simples (sem dependências) — usado para a tabela de referência de risco renal. */
export function Dialog({ open, onClose, title, description, children }: DialogProps) {
  if (!open) return null;
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(14,37,45,0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#fff', borderRadius: 16,
          width: '100%', maxWidth: 640,
          maxHeight: '85vh', overflowY: 'auto',
          padding: '24px 24px 20px',
          boxShadow: '0 12px 40px rgba(14,37,45,0.18)',
          display: 'flex', flexDirection: 'column', gap: 14,
        }}
        onClick={e => e.stopPropagation()}
      >
        <div>
          <h3 style={{ fontSize: 17, fontWeight: 800, color: 'var(--ink)' }}>{title}</h3>
          {description && <p style={{ fontSize: 13, color: 'var(--pen2)', marginTop: 4 }}>{description}</p>}
        </div>
        {children}
        <Button variant="outline" onClick={onClose}>Fechar</Button>
      </div>
    </div>
  );
}

interface CardProps {
  children: ReactNode;
  accentColor?: string;
  style?: React.CSSProperties;
}

export function Card({ children, accentColor, style }: CardProps) {
  return (
    <div
      style={{
        background: '#fff',
        border: `1px solid ${accentColor ?? 'var(--line)'}`,
        borderRadius: 12,
        boxShadow: '0 1px 2px rgba(14,37,45,0.05)',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  iconColor?: string;
}

export function CardHeader({ icon, title, description, iconColor }: CardHeaderProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {icon && <span style={{ color: iconColor ?? 'var(--petrol)', display: 'flex' }}>{icon}</span>}
        <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.01em' }}>{title}</span>
      </div>
      {description && (
        <p style={{ fontSize: 13.5, color: 'var(--pen2)', lineHeight: 1.5 }}>{description}</p>
      )}
    </div>
  );
}

export function Separator() {
  return <div style={{ height: 1, background: 'var(--line2)', margin: '4px 0' }} />;
}

interface SubHeadingProps {
  children: ReactNode;
  hint?: string;
}

export function SubHeading({ children, hint }: SubHeadingProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
      <h4 style={{ fontSize: 12, fontWeight: 700, color: 'var(--pen)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {children}
      </h4>
      {hint && <span style={{ fontSize: 11, color: 'var(--pen3)' }}>{hint}</span>}
    </div>
  );
}

interface CheckItemProps {
  checked: boolean | undefined;
  onChange: (v: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  error?: boolean;
}

/** Linha de checkbox estilo "card row" (rótulo + descrição opcional), usada para campos booleanos. */
export function CheckItem({ checked, onChange, label, description, error }: CheckItemProps) {
  return (
    <label
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        padding: '8px 10px',
        borderRadius: 8,
        cursor: 'pointer',
        border: error ? '1px solid var(--red)' : '1px solid transparent',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--paper2, #f6f7f5)'; }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
    >
      <input
        type="checkbox"
        checked={!!checked}
        onChange={e => onChange(e.target.checked)}
        style={{ marginTop: 3, width: 16, height: 16, flexShrink: 0, accentColor: 'var(--petrol)' }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.4 }}>{label}</span>
        {description && (
          <span style={{ fontSize: 12, color: 'var(--pen2)', lineHeight: 1.4 }}>{description}</span>
        )}
      </div>
    </label>
  );
}
