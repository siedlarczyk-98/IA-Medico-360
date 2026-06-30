import { formSpecRegistry, type FormSpec } from './formSpecs';

const spec: FormSpec = {
  sections: [
    {
      title: 'Demografia',
      fields: [
        { key: 'idade' },
        { key: 'sexo' },
      ],
    },
    {
      title: 'Perfil clínico — PREVENT',
      fields: [
        { key: 'ct_mgdl' },
        { key: 'hdl_mgdl' },
        { key: 'ldl_mgdl' },
        { key: 'sbp_mmhg' },
        { key: 'bmi' },
        { key: 'egfr' },
        { key: 'fumante' },
        { key: 'antihtn_use' },
        { key: 'statin_use' },
        { key: 'hipertensao' },
        { key: 'hipercolesterolemia_familiar' },
      ],
    },
    {
      title: 'Fluxograma de Estratificação SBC 2025',
      isDivider: true,
      fields: [],
      dividerDescription: 'Os campos abaixo determinam a categoria de risco pelo algoritmo da Diretriz Brasileira (Tabela 4.1 / Figura 4.1).',
    },
    {
      title: 'Evento cardiovascular prévio',
      fields: [
        { key: 'evento_cv_previo' },
        {
          key: 'tipos_evento_cv',
          visibleWhen: [{ field: 'evento_cv_previo', equals: true }],
        },
      ],
    },
    {
      title: 'Doença aterosclerótica e marcadores',
      fields: [
        { key: 'doenca_aterosclerotica_significativa' },
        { key: 'cac_ua' },
        { key: 'cac_percentil_gt75' },
        { key: 'placa_carotidea_lt50' },
        { key: 'placa_angiotc_lt50' },
        { key: 'aaa_conhecido' },
        { key: 'lpa_mgdl' },
        { key: 'lpa_nmol' },
      ],
    },
    {
      title: 'Diabetes mellitus',
      fields: [
        { key: 'diabetes' },
        { key: 'tipo_dm',                      visibleWhen: [{ field: 'diabetes', equals: true }] },
        { key: 'duracao_dm_anos',               visibleWhen: [{ field: 'diabetes', equals: true }] },
        { key: 'dm1_diagnosticado_apos_18_anos', visibleWhen: [{ field: 'diabetes', equals: true }, { field: 'tipo_dm', equals: 'dm1' }] },
        { key: 'albuminuria_mg_g',              visibleWhen: [{ field: 'diabetes', equals: true }] },
        { key: 'historia_familiar_dac_prematura', visibleWhen: [{ field: 'diabetes', equals: true }] },
        { key: 'sindrome_metabolica',           visibleWhen: [{ field: 'diabetes', equals: true }] },
        { key: 'neuropatia_autonoma_incipiente', visibleWhen: [{ field: 'diabetes', equals: true }] },
        { key: 'neuropatia_autonoma_instalada', visibleWhen: [{ field: 'diabetes', equals: true }] },
        { key: 'retinopatia_np_leve',           visibleWhen: [{ field: 'diabetes', equals: true }] },
        { key: 'retinopatia_avancada',          visibleWhen: [{ field: 'diabetes', equals: true }] },
      ],
    },
    {
      title: 'Critério de risco extremo',
      collapsible: true,
      fields: [
        { key: 'cirurgia_revasc_previa_fora_evento' },
        { key: 'ldl_persistente_ge100_max_tto' },
        { key: 'evento_agudo_lt2anos' },
      ],
    },
    {
      title: 'Fatores agravantes',
      collapsible: true,
      fields: [
        { key: 'historia_familiar_cv_prematura' },
        { key: 'adiposidade_com_param_alterado' },
        { key: 'esteatose_hepatica' },
        { key: 'doenca_inflamatoria_cronica' },
        { key: 'transplante_orgao_solido' },
        { key: 'fatores_femininos' },
        { key: 'pcr_us_mgL' },
      ],
    },
  ],
};

formSpecRegistry['risco_cv_sbc2025'] = spec;
