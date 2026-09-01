/**
 * Contrato do onboarding, compartilhado pelos três apps.
 *
 * A lista de pendências é calculada NO SERVIDOR (`app/medicina/identidade.py`).
 * Nenhum app decide o que falta: eles renderizam o que vem. É isso que permite
 * acrescentar uma exigência nova no backend e os três herdarem de graça — sem
 * isso, uma regra nova viraria três mudanças e três divergências, que é como
 * este repo acabou com três listas de especialidade diferentes.
 */

export type Pendencia =
  | 'aceite_termos'
  | 'nome'
  | 'med_status'
  | 'crm'
  | 'especialidade';

export interface Perfil {
  id: string;
  email: string;
  name: string | null;
  crm: string | null;
  crm_state: string | null;
  med_status: string | null;
  specialty: string | null;
  specialty_slug: string | null;
  /** `cadastro` | `waid_grupo` | `cfm` | `declarado` | `admin` */
  specialty_source: string | null;
  /** Falso quando a especialidade veio de fonte automática — o campo tranca. */
  specialty_editavel: boolean;
  onboarding_complete: boolean;
  onboarding_pendencias: Pendencia[];
  /**
   * Estágios de carreira compatíveis com o que o servidor já sabe. Estar num
   * grupo `[CFM]` prova que existe CRM, então "aluno de graduação" sai da lista;
   * ter especialidade registrada elimina também "generalista".
   *
   * Vazio = o servidor não opinou (contrato antigo): a tela mostra os quatro.
   */
  med_status_opcoes?: string[];
}

export interface Especialidade {
  slug: string;
  nome: string;
}

export interface RespostaOnboarding {
  access_token: string;
  onboarding_complete: boolean;
  onboarding_pendencias: Pendencia[];
}

/** Só o que o médico ainda precisa informar — o resto chega sozinho. */
export interface DadosOnboarding {
  med_status: string;
  terms_accepted: boolean;
  name?: string;
  crm?: string;
  crm_state?: string;
  specialty?: string;
  enrollment_year?: number;
}

export const MED_STATUS_OPCOES = [
  { valor: 'graduando', rotulo: 'Aluno de graduação' },
  { valor: 'generalista', rotulo: 'Médico generalista' },
  { valor: 'residente', rotulo: 'Médico residente' },
  { valor: 'especialista', rotulo: 'Médico especialista' },
] as const;

export const UFS = [
  'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
  'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
  'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO',
] as const;
