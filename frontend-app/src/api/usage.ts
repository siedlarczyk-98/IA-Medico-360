import { getToken } from '../lib/auth';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export interface UsageResponse {
  has_limit: boolean;
  usage_percentage: number | null;
  week_reset_at: string | null;
}

export async function getUserUsage(): Promise<UsageResponse> {
  const token = getToken();
  const res = await fetch(`${BASE}/api/v1/users/usage`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Failed to fetch usage');
  return res.json();
}
