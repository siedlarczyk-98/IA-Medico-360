import { useMutation } from '@tanstack/react-query';
import { calculatePrevent } from '../api/prevent';

export function usePreventCalculator() {
  return useMutation({ mutationFn: calculatePrevent });
}
