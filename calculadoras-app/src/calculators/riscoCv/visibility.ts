import type { CalculatorField } from '../../api/calculators';
import type { FormSpec } from '../formSpecs';
import { checkVisibleCond } from '../formHelpers';

/**
 * Fábrica de `isFieldVisible(key)` que lê a condição `visibleWhen` declarada no
 * formSpec para o campo (mesma fonte usada por DynamicCalculatorForm/buildVisibleInputs),
 * para as telas dedicadas desta calculadora não duplicarem/divergirem dessa lógica.
 */
export function makeFieldVisibility(
  formSpec: FormSpec | undefined,
  stepKey: string,
  values: Record<string, unknown>
): (fieldKey: string) => boolean {
  const conditions = new Map<string, FormSpec['sections'][number]['fields'][number]['visibleWhen']>();
  if (formSpec) {
    for (const section of formSpec.sections) {
      if (section.step !== stepKey) continue;
      for (const f of section.fields) {
        conditions.set(f.key, f.visibleWhen);
      }
    }
  }
  return (fieldKey: string) => {
    const cond = conditions.get(fieldKey);
    if (!cond || cond.length === 0) return true;
    return cond.every(c => checkVisibleCond(c, values));
  };
}

export function pickField(fields: CalculatorField[], key: string): CalculatorField | undefined {
  return fields.find(f => f.key === key);
}
