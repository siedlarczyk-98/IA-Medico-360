import { useQuery } from '@tanstack/react-query';
import { getCalculator } from '../api/calculators';

export function useCalculatorDetail(slug: string) {
  return useQuery({
    queryKey: ['calculator', slug],
    queryFn: () => getCalculator(slug),
    staleTime: 10 * 60 * 1000,
  });
}
