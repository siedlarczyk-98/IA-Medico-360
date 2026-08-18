import type { ReactNode } from 'react';

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

export function FieldDescription({ children }: { children: ReactNode }) {
  return <p style={{ fontSize: 12, color: 'var(--pen2)', lineHeight: 1.5, marginTop: -8 }}>{children}</p>;
}

export function FieldGroup({ children }: { children: ReactNode }) {
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>{children}</div>;
}
