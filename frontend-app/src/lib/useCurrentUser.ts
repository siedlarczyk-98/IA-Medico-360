import { getTokenPayload } from './auth';

const MED_STATUS_LABEL: Record<string, string> = {
  graduando: 'Graduação',
  generalista: 'Clínico Geral',
  residente: 'Residência',
  especialista: 'Especialista',
};

export function useCurrentUser() {
  const payload = getTokenPayload();
  if (!payload) return null;

  const firstName = payload.name?.split(' ')[0] ?? null;
  const crmLabel = payload.crm && payload.crm_state
    ? `CRM/${payload.crm_state} ${payload.crm}`
    : null;
  const initial = payload.name?.[0]?.toUpperCase() ?? '?';
  const medStatusLabel = payload.med_status
    ? (MED_STATUS_LABEL[payload.med_status] ?? payload.med_status)
    : null;

  return {
    name: payload.name,
    firstName,
    crmLabel,
    initial,
    medStatusLabel,
    role: payload.role,
  };
}
