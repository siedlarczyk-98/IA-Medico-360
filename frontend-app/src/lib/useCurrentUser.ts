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
  // O `sub` do JWT entra na chave DE PROPÓSITO.
  //
  // Com a chave fixa `['currentUser']`, trocar de médico no mesmo navegador
  // mantinha o dado do anterior em cache por até 5 minutos: a sessão já era da
  // pessoa certa, mas a saudação e o card do rodapé mostravam o nome e o CRM de
  // quem tinha usado antes. Observado em produção ao trocar de conta no LMS.
  //
  // Invalidar na hora do login resolveria o caso previsto; a chave por
  // identidade resolve TODOS, porque um usuário nunca consegue ler a entrada de
  // outro — a chave simplesmente não bate.
  // As invalidações no `Sidebar` passam só `['currentUser']` e continuam
  // valendo: o `invalidateQueries` casa por PREFIXO. Não as troque para
  // `exact: true` sem passar o `sub` junto, ou o perfil para de atualizar
  // depois de salvo.
  const sub = getTokenPayload()?.sub ?? null;

  const { data: user } = useQuery<UserResponse | null>({
    queryKey: ['currentUser', sub],
    queryFn: getMe,
    enabled: sub != null,
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
