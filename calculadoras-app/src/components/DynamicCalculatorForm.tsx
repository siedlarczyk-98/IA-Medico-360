import { useState } from 'react';
import type { CalculatorField } from '../api/calculators';
import type { FormSpec, VisibleWhen } from '../calculators/formSpecs';
import { FieldWidget } from './FieldWidget';

interface Props {
  fields: CalculatorField[];
  formSpec?: FormSpec;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  aiFilledKeys?: Set<string>;
  fieldErrors?: Record<string, string>;
  showErrors?: boolean;
}

function checkCondition(cond: VisibleWhen, values: Record<string, unknown>): boolean {
  const v = values[cond.field];
  if (cond.equals !== undefined)    return v === cond.equals;
  if (cond.notEquals !== undefined) return v !== cond.notEquals;
  if (cond.includes !== undefined)  return Array.isArray(v) && (v as unknown[]).includes(cond.includes);
  return true;
}

function isVisible(conditions: VisibleWhen[] | undefined, values: Record<string, unknown>): boolean {
  if (!conditions || conditions.length === 0) return true;
  return conditions.every(c => checkCondition(c, values));
}

const sectionHeaderStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: 'var(--petrol)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  padding: '10px 0 8px',
  borderBottom: '1px solid var(--line2)',
  marginBottom: 12,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  cursor: 'pointer',
  userSelect: 'none',
};

export function DynamicCalculatorForm({ fields, formSpec, values, onChange, aiFilledKeys, fieldErrors, showErrors }: Props) {
  const fieldMap = new Map(fields.map(f => [f.key, f]));

  const [collapsed, setCollapsed] = useState<Set<number>>(
    () => new Set(formSpec?.sections.map((s, i) => s.collapsible ? i : -1).filter(i => i >= 0))
  );

  function toggleSection(i: number) {
    setCollapsed(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  }

  if (!formSpec) {
    const sorted = [...fields].sort((a, b) => a.display_order - b.display_order);
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {sorted.map(f => (
          <FieldWidget
            key={f.key}
            field={f}
            value={values[f.key]}
            onChange={v => onChange(f.key, v)}
            aiPrefilled={aiFilledKeys?.has(f.key)}
            error={fieldErrors?.[f.key]}
            showError={showErrors}
          />
        ))}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {formSpec.sections.map((section, si) => {
        if (!isVisible(section.visibleWhen, values)) return null;

        if (section.isDivider) {
          return (
            <div key={si} style={{ margin: '8px 0 20px', paddingTop: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: section.dividerDescription ? 8 : 0 }}>
                <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>
                  {section.title}
                </span>
                <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
              </div>
              {section.dividerDescription && (
                <p style={{ fontSize: 12, color: 'var(--pen2)', textAlign: 'center', lineHeight: 1.5 }}>
                  {section.dividerDescription}
                </p>
              )}
            </div>
          );
        }

        const isOpen = !collapsed.has(si);
        const visibleFields = section.fields.filter(
          f => fieldMap.has(f.key) && isVisible(f.visibleWhen, values)
        );

        return (
          <div key={si} style={{ marginBottom: 4 }}>
            <div
              style={sectionHeaderStyle}
              onClick={() => section.collapsible && toggleSection(si)}
            >
              <span>{section.title}</span>
              {section.collapsible && (
                <span style={{ fontSize: 11, color: 'var(--pen3)', transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}>▲</span>
              )}
            </div>

            {isOpen && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingBottom: 20 }}>
                {visibleFields.map(f => {
                  const fieldDef = fieldMap.get(f.key)!;
                  return (
                    <FieldWidget
                      key={f.key}
                      field={fieldDef}
                      value={values[f.key]}
                      onChange={v => onChange(f.key, v)}
                      aiPrefilled={aiFilledKeys?.has(f.key)}
                      error={fieldErrors?.[f.key]}
                      showError={showErrors}
                    />
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
