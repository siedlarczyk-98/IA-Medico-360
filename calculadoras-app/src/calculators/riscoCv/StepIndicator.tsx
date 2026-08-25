interface StepIndicatorProps {
  steps: string[];
  currentStep: number;
  completedSteps: number[];
}

/**
 * Indicador de progresso do wizard "Risco CV — SBC 2025".
 * Isolado deste calculador (não é o WizardStepper genérico usado pelo motor de
 * formSpec) para reproduzir fielmente a estrutura visual do app de referência —
 * círculos numerados centralizados, com check ao completar e linha conectora —
 * recolorido com os tokens deste projeto.
 */
export function StepIndicator({ steps, currentStep, completedSteps }: StepIndicatorProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'center', gap: 4, flexWrap: 'wrap', padding: '18px 8px 22px' }}>
      {steps.map((label, i) => {
        const isComplete = completedSteps.includes(i);
        const isActive = i === currentStep;
        const circleBg = isComplete ? 'var(--green)' : isActive ? 'var(--petrol)' : '#fff';
        const circleBorder = isComplete ? 'var(--green)' : isActive ? 'var(--petrol)' : 'var(--line)';
        const circleColor = isComplete || isActive ? '#fff' : 'var(--pen3)';
        const labelColor = isActive ? 'var(--ink)' : isComplete ? 'var(--pen)' : 'var(--pen3)';

        return (
          <div key={label} style={{ display: 'flex', alignItems: 'flex-start', gap: 4 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 68 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12.5,
                  fontWeight: 700,
                  flexShrink: 0,
                  background: circleBg,
                  border: `2px solid ${circleBorder}`,
                  color: circleColor,
                  boxShadow: isActive ? '0 2px 8px rgba(1,71,81,0.25)' : 'none',
                  transition: 'background 0.15s, border-color 0.15s',
                }}
              >
                {isComplete ? '✓' : i + 1}
              </div>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: isActive ? 700 : 600,
                  color: labelColor,
                  textAlign: 'center',
                  lineHeight: 1.25,
                  maxWidth: 76,
                }}
              >
                {label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                style={{
                  width: 24,
                  height: 2,
                  marginTop: 15,
                  background: isComplete ? 'var(--green)' : 'var(--line2)',
                  flexShrink: 0,
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
