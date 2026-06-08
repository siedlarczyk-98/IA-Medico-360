import { useEffect, useState } from 'react';
import { getTokenPayload } from './auth';
import { getMe, type UserResponse } from '../api/auth';

const MED_STATUS_LABEL: Record<string, string> = {
  graduando: 'Graduação',
  generalista: 'Clínico Geral',
  residente: 'Residência',
  especialista: 'Especialista',
};

export function useCurrentUser() {
  const [user, setUser] = useState<UserResponse | null>(null);

  useEffect(() => {
    const payload = getTokenPayload();
    if (!payload) return;
    getMe().then(setUser).catch(() => {});
  }, []);

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
    name: user.name,
    firstName,
    crmLabel,
    initial,
    medStatusLabel,
    role: user.role,
  };
}
