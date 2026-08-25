import type { RiskLevel, WizardState } from '../riskTypes';

/** Contrato de props dos steps do wizard — porta literal do padrão da referência. */
export interface WizardStepProps {
  state: WizardState;
  onChange: (updates: Partial<WizardState>) => void;
  onResult: (level: RiskLevel) => void;
  onNext: () => void;
  onBack?: () => void;
}
