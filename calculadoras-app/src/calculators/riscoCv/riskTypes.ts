/**
 * Estado do wizard "Risco CV — SBC 2025" — porta literal de
 * `Cardiac Risk Stratifier/src/lib/riskTypes.ts` (app de referência).
 * Cálculo 100% client-side; nenhum campo aqui é enviado ao backend, exceto
 * os coletados no Step4 (PREVENT), que chama `POST /calculators/.../execute`
 * só para obter o escore (ver steps/Step4Prevent.tsx).
 */

export type RiskLevel = 'low' | 'intermediate' | 'high' | 'very-high' | 'extreme';

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: 'Baixo',
  intermediate: 'Intermediário',
  high: 'Alto',
  'very-high': 'Muito Alto',
  extreme: 'Extremo',
};

export interface RiskGoal {
  level: RiskLevel;
  ldlGoal: string;
  nonHdlGoal: string;
  ldlReduction: string;
  apoB?: string;
  pharmacotherapy: string[];
}

export const RISK_GOALS: Record<RiskLevel, RiskGoal> = {
  low: {
    level: 'low',
    ldlGoal: '< 115 mg/dL',
    nonHdlGoal: '< 145 mg/dL',
    ldlReduction: '≥ 30%',
    apoB: '< 100 mg/dL',
    pharmacotherapy: ['Mudança de estilo de vida (MEV)', 'Estatina de baixa/moderada potência se necessário'],
  },
  intermediate: {
    level: 'intermediate',
    ldlGoal: '< 100 mg/dL',
    nonHdlGoal: '< 130 mg/dL',
    ldlReduction: '≥ 30–50%',
    apoB: '< 90 mg/dL',
    pharmacotherapy: ['Mudança de estilo de vida (MEV)', 'Estatina de moderada potência'],
  },
  high: {
    level: 'high',
    ldlGoal: '< 70 mg/dL',
    nonHdlGoal: '< 100 mg/dL',
    ldlReduction: '≥ 50%',
    apoB: '< 70 mg/dL',
    pharmacotherapy: ['Estatina de alta potência', 'Associar Ezetimiba se meta não atingida'],
  },
  'very-high': {
    level: 'very-high',
    ldlGoal: '< 50 mg/dL',
    nonHdlGoal: '< 80 mg/dL',
    ldlReduction: '≥ 50%',
    apoB: '< 55 mg/dL',
    pharmacotherapy: [
      'Estatina de alta potência',
      'Associar Ezetimiba',
      'Considerar inibidor de PCSK9 se meta não atingida',
    ],
  },
  extreme: {
    level: 'extreme',
    ldlGoal: '< 40 mg/dL',
    nonHdlGoal: '< 70 mg/dL',
    ldlReduction: '≥ 50%',
    apoB: '< 45 mg/dL',
    pharmacotherapy: [
      'Estatina de alta potência + Ezetimiba',
      'Inibidor de PCSK9 (Evolocumabe ou Alirocumabe)',
      'Considerar Ácido Bempedóico se intolerância a estatina',
      'Considerar Inclisirana',
    ],
  },
};

export interface WizardState {
  // Step 1 — Very High / Extreme
  dcvaManifesta: boolean;
  cac300: boolean;
  nenhumVeryHigh: boolean;
  eventosMaiores: string[];
  condicoesAltoRisco: string[];

  // Step 2 — Diabetes
  hasDM: boolean | null;
  dmAge: string;
  dmSex: 'M' | 'F';
  dm2EmarItems: string[];
  dm2EarItems: string[];

  // Step 3 — High Risk
  ateroscleroseSubclinica: boolean;
  ldl190: boolean;
  lpa180: boolean;
  cac100a300: boolean;

  // Step 4 — PREVENT (calculado via backend; ver Step4Prevent.tsx)
  sexo: 'M' | 'F';
  idade: string;
  ctMgdl: string;
  hdlMgdl: string;
  sbpMmhg: string;
  bmi: string;
  egfr: string;
  fumante: boolean;
  antihtnUse: boolean;
  statinUse: boolean;
  ldlMgdl: string;
  preventScore: number | null;

  // Step 5 — Aggravating factors
  aggravatingFactors: string[];
}

export const INITIAL_STATE: WizardState = {
  dcvaManifesta: false,
  cac300: false,
  nenhumVeryHigh: false,
  eventosMaiores: [],
  condicoesAltoRisco: [],

  hasDM: null,
  dmAge: '',
  dmSex: 'M',
  dm2EmarItems: [],
  dm2EarItems: [],

  ateroscleroseSubclinica: false,
  ldl190: false,
  lpa180: false,
  cac100a300: false,

  sexo: 'M',
  idade: '',
  ctMgdl: '',
  hdlMgdl: '',
  sbpMmhg: '',
  bmi: '',
  egfr: '',
  fumante: false,
  antihtnUse: false,
  statinUse: false,
  ldlMgdl: '',
  preventScore: null,

  aggravatingFactors: [],
};
