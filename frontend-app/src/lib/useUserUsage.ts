import { useEffect, useState } from 'react';
import { getUserUsage, type UsageResponse } from '../api/usage';

interface UseUserUsageResult {
  hasLimit: boolean;
  usagePercentage: number | null;
  weekResetAt: Date | null;
  loading: boolean;
}

export function useUserUsage(refreshTrigger = 0): UseUserUsageResult {
  const [data, setData] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getUserUsage()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [refreshTrigger]);

  return {
    hasLimit: data?.has_limit ?? false,
    usagePercentage: data?.usage_percentage ?? null,
    weekResetAt: data?.week_reset_at ? new Date(data.week_reset_at) : null,
    loading,
  };
}
