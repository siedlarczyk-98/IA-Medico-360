import { useQuery } from '@tanstack/react-query';
import { getTokenPayload } from './auth';
import { getMe, type UserResponse } from '../api/auth';

const MED_STATUS_LABEL: Record<string, string> = {
  graduando: 'Graduação',
  generalista: 'Clínico Geral',
  residente: 'Residência',
  especialista: 'Especialista',
};

export function useCurrentUser() {
  const { data: user } = useQuery<UserResponse | null>({
    queryKey: ['currentUser'],
    queryFn: getMe,
    enabled: getTokenPayload() != null,
    staleTime: 5 * 60 * 1000,
  });

  if (!user) return null;

  const firstName = user.name?.split(' ')[0] ?? null;
  const crmLabel = user.crm && user.crm_state
    ? `CRM/${user.crm_state} ${user.crm}`
    : null;
  const initial = user.name?.[0]?.toUpperCase() ?? '?';
  const medStatusLabel = user.med_status
    ? (MED_STATUS_LABEL[user.med_status] ?? user.med_status)
    : null;

  return {
    id: user.id,
    name: user.name,
    email: user.email,
    intercomUserHash: user.intercom_user_hash ?? null,
    firstName,
    crmLabel,
    initial,
    medStatusLabel,
    role: user.role,
  };
}
