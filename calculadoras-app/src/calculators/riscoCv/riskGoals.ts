import type { RiscoCvResult } from '../../api/calculators';

export interface RiskGoal {
  ldlGoal: string;
  nonHdlGoal: string;
  ldlReduction: string;
  apoB?: string;
  pharmacotherapy: string[];
}

/**
 * Metas terapêuticas e recomendações farmacológicas por categoria de risco —
 * Diretriz Brasileira de Dislipidemias e Prevenção da Aterosclerose (SBC 2025).
 * Conteúdo complementar ao `meta_ldl_recomendada` já calculado pelo backend
 * (app/calculators/formulas/cardiologia/risco_cv_sbc2025.py).
 */
export const RISK_GOALS: Record<RiscoCvResult['categoria'], RiskGoal> = {
  BAIXO: {
    ldlGoal: '< 115 mg/dL',
    nonHdlGoal: '< 145 mg/dL',
    ldlReduction: '≥ 30%',
    apoB: '< 100 mg/dL',
    pharmacotherapy: ['Mudança de estilo de vida (MEV)', 'Estatina de baixa/moderada potência se necessário'],
  },
  INTERMEDIARIO: {
    ldlGoal: '< 100 mg/dL',
    nonHdlGoal: '< 130 mg/dL',
    ldlReduction: '≥ 30–50%',
    apoB: '< 90 mg/dL',
    pharmacotherapy: ['Mudança de estilo de vida (MEV)', 'Estatina de moderada potência'],
  },
  ALTO: {
    ldlGoal: '< 70 mg/dL',
    nonHdlGoal: '< 100 mg/dL',
    ldlReduction: '≥ 50%',
    apoB: '< 70 mg/dL',
    pharmacotherapy: ['Estatina de alta potência', 'Associar Ezetimiba se meta não atingida'],
  },
  MUITO_ALTO: {
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
  EXTREMO: {
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
