import { useMutation } from '@tanstack/react-query';
import { extractFields } from '../api/calculators';

export function useExtractFields(slug: string) {
  return useMutation({
    mutationFn: (text: string) => extractFields(slug, text),
  });
}
