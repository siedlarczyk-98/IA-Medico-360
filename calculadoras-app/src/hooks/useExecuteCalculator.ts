import { useMutation } from '@tanstack/react-query';
import { executeCalculator } from '../api/calculators';

interface ExecuteVars {
  inputs: Record<string, unknown>;
  dryRun?: boolean;
}

export function useExecuteCalculator(slug: string) {
  return useMutation({
    mutationFn: ({ inputs, dryRun }: ExecuteVars) => executeCalculator(slug, inputs, dryRun),
  });
}
