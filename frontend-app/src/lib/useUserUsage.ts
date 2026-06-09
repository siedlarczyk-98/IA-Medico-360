import { useQuery } from '@tanstack/react-query';
import { getUserUsage, type UsageResponse } from '../api/usage';

interface UseUserUsageResult {
  hasLimit: boolean;
  usagePercentage: number | null;
  weekResetAt: Date | null;
  loading: boolean;
}

export function useUserUsage(refreshTrigger = 0): UseUserUsageResult {
  const { data, isLoading } = useQuery<UsageResponse | null>({
    // refreshTrigger entra na chave: muda após cada resposta para revalidar o uso.
    queryKey: ['userUsage', refreshTrigger],
    queryFn: getUserUsage,
    staleTime: 30 * 1000,
  });

  return {
    hasLimit: data?.has_limit ?? false,
    usagePercentage: data?.usage_percentage ?? null,
    weekResetAt: data?.week_reset_at ? new Date(data.week_reset_at) : null,
    loading: isLoading,
  };
}
