import type { CalculatorField } from '../api/calculators';
import type { FormSpec, VisibleWhen } from './formSpecs';

export function checkVisibleCond(cond: VisibleWhen, values: Record<string, unknown>): boolean {
  const v = values[cond.field];
  if (cond.equals !== undefined)    return v === cond.equals;
  if (cond.notEquals !== undefined) return v !== cond.notEquals;
  if (cond.includes !== undefined)  return Array.isArray(v) && (v as unknown[]).includes(cond.includes);
  return true;
}

export function isVisibleSection(conditions: VisibleWhen[] | undefined, values: Record<string, unknown>): boolean {
  if (!conditions || conditions.length === 0) return true;
  return conditions.every(c => checkVisibleCond(c, values));
}

/** Reduz `values` às chaves de campos atualmente visíveis, segundo o `formSpec` (ou todos os `fields`, se não houver formSpec). */
export function buildVisibleInputs(
  values: Record<string, unknown>,
  fields: CalculatorField[],
  formSpec: FormSpec | undefined
): Record<string, unknown> {
  if (!formSpec) {
    const out: Record<string, unknown> = {};
    for (const f of fields) {
      if (values[f.key] !== undefined) out[f.key] = values[f.key];
    }
    return out;
  }

  const visibleKeys = new Set<string>();
  for (const section of formSpec.sections) {
    if (!isVisibleSection(section.visibleWhen, values)) continue;
    for (const f of section.fields) {
      if (!f.visibleWhen || f.visibleWhen.every(c => checkVisibleCond(c, values))) {
        visibleKeys.add(f.key);
      }
    }
  }

  const out: Record<string, unknown> = {};
  for (const key of visibleKeys) {
    if (values[key] !== undefined) out[key] = values[key];
  }
  return out;
}

/** Erros "campo obrigatório" para os campos requeridos e visíveis (todos, se `visibleKeys` for omitido). */
export function validateRequired(
  values: Record<string, unknown>,
  fields: CalculatorField[],
  visibleKeys?: Set<string>
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const f of fields) {
    if (!f.required) continue;
    if (visibleKeys && !visibleKeys.has(f.key)) continue;
    const v = values[f.key];
    if (v === undefined || v === null || v === '') {
      errors[f.key] = 'Campo obrigatório';
    }
  }
  return errors;
}
