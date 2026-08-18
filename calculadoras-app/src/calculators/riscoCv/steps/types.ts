import type { CalculatorField } from '../../../api/calculators';
import type { FormSpec } from '../../formSpecs';

export interface StepProps {
  fields: CalculatorField[];
  formSpec: FormSpec | undefined;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  aiFilledKeys?: Set<string>;
  fieldErrors?: Record<string, string>;
  showErrors?: boolean;
}
