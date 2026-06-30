import { useQuery } from '@tanstack/react-query';
import { listCalculators } from '../api/calculators';

export function useCalculators(specialty?: string) {
  return useQuery({
    queryKey: ['calculators', specialty],
    queryFn: () => listCalculators(specialty),
    staleTime: 10 * 60 * 1000,
  });
}
