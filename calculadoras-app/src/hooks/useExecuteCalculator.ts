import { useMutation } from '@tanstack/react-query';
import { executeCalculator } from '../api/calculators';

export function useExecuteCalculator(slug: string) {
  return useMutation({
    mutationFn: (inputs: Record<string, unknown>) => executeCalculator(slug, inputs),
  });
}
