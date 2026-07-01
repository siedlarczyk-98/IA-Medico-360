import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { CalculatorListItem } from '../api/calculators';
import { favoriteCalculator, unfavoriteCalculator } from '../api/calculators';

interface ToggleParams {
  id: string;
  slug: string;
  nextValue: boolean;
}

export function useToggleFavorite() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ slug, nextValue }: ToggleParams) =>
      nextValue ? favoriteCalculator(slug) : unfavoriteCalculator(slug),
    onMutate: async ({ id, nextValue }: ToggleParams) => {
      await queryClient.cancelQueries({ queryKey: ['calculators'] });
      const previous = queryClient.getQueriesData<CalculatorListItem[]>({ queryKey: ['calculators'] });

      queryClient.setQueriesData<CalculatorListItem[]>({ queryKey: ['calculators'] }, old =>
        old?.map(c => (c.id === id ? { ...c, is_favorite: nextValue } : c))
      );

      return { previous };
    },
    onError: (_err, _vars, context) => {
      context?.previous.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['calculators'] });
    },
  });
}
