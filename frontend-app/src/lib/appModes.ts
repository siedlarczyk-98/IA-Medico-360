export type AppMode = 'orquestrador' | 'agregador';

export const MODE_INTRO_SEEN_KEY = 'm360_mode_intro_seen';
export const MODE_PREFERENCE_KEY = 'm360_preferred_mode';

export interface AppModeInfo {
  key: AppMode;
  label: string;
  shortLabel: string;
  tagline: string;
  desc: string;
  bullets: string[];
}

/**
 * Modos expostos na interface.
 *
 * O Agregador foi retirado daqui: o produto passou a ser o Orquestrador. A
 * remoção é só de superfície — o backend, as rotas `/agregador/*` e os testes
 * continuam intactos, e as conversas antigas seguem no banco. Para trazê-lo de
 * volta, este array é o ponto de partida (ver git para o que foi removido de
 * App.tsx e Topbar.tsx junto).
 *
 * O tipo `AppMode` mantém 'agregador' porque conversas gravadas ainda carregam
 * `feature: 'AGREGADOR'` e precisam ser reconhecidas para serem filtradas.
 */
export const APP_MODES: AppModeInfo[] = [
  {
    key: 'orquestrador',
    label: 'Orquestrador',
    shortLabel: 'Orq.',
    tagline: 'Recomendado para o dia a dia',
    desc: 'Respostas com validação em bases científicas e artigos. Escolha o modo ideal — busca rápida, raciocínio clínico, checagem farmacológica ou produtividade.',
    bullets: [
      'A plataforma escolhe e valida a resposta pra você',
      'Checa citações em fontes científicas (PubMed, diretrizes)',
      'Ideal se você não quer se preocupar com qual IA usar',
    ],
  },
];
