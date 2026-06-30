import { useQuery } from '@tanstack/react-query';
import { getMe, type UserResponse } from '../api/auth';
import { getTokenPayload } from './auth';

export function useCurrentUser() {
  const { data: user } = useQuery<UserResponse | null>({
    queryKey: ['currentUser'],
    queryFn: getMe,
    enabled: getTokenPayload() != null,
    staleTime: 5 * 60 * 1000,
  });

  if (!user) return null;

  const firstName = user.name?.split(' ')[0] ?? null;
  const crmLabel = user.crm && user.crm_state ? `CRM/${user.crm_state} ${user.crm}` : null;
  const initial = user.name?.[0]?.toUpperCase() ?? '?';

  return { id: user.id, name: user.name, email: user.email, firstName, crmLabel, initial, role: user.role };
}
