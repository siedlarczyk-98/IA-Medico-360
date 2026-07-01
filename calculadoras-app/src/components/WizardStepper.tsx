import type { WizardStep } from '../calculators/formSpecs';

interface Props {
  steps: WizardStep[];
  activeIndex: number;
}

export function WizardStepper({ steps, activeIndex }: Props) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'center', gap: 0, padding: '18px 8px 22px' }}>
      {steps.map((step, i) => {
        const isDone = i < activeIndex;
        const isActive = i === activeIndex;
        const circleColor = isDone ? 'var(--green)' : isActive ? 'var(--petrol)' : 'var(--line2)';
        const textColor = isActive ? 'var(--ink)' : isDone ? 'var(--pen)' : 'var(--pen3)';

        return (
          <div key={step.key} style={{ display: 'flex', alignItems: 'center', flex: i < steps.length - 1 ? 1 : undefined }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 64 }}>
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  background: isDone || isActive ? circleColor : '#fff',
                  border: `2px solid ${circleColor}`,
                  color: isDone || isActive ? '#fff' : 'var(--pen3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {isDone ? '✓' : i + 1}
              </div>
              <span style={{ fontSize: 11, fontWeight: isActive ? 700 : 600, color: textColor, whiteSpace: 'nowrap' }}>
                {step.title}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div style={{ flex: 1, height: 2, background: isDone ? 'var(--green)' : 'var(--line2)', margin: '0 4px', minWidth: 16, alignSelf: 'flex-start', marginTop: 13 }} />
            )}
          </div>
        );
      })}
    </div>
  );
}
