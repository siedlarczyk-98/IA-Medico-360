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
  {
    key: 'agregador',
    label: 'Agregador',
    shortLabel: 'Agr.',
    tagline: 'Para comparar ferramentas',
    desc: 'Escolha a ferramenta que mais se adapta à sua necessidade. Acesse diretamente Claude, GPT, Gemini e outros — sem triagem automática.',
    bullets: [
      'Você escolhe manualmente qual IA usar',
      'Sem validação científica automática das respostas',
      'Ideal se você já sabe qual modelo prefere usar',
    ],
  },
];
