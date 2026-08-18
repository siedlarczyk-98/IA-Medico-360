import { formSpecRegistry, type FormSpec } from './formSpecs';

const spec: FormSpec = {
  sections: [
    {
      title: 'Dados do paciente',
      fields: [
        { key: 'idade' },
        { key: 'sexo' },
      ],
    },
    {
      title: 'CHA2DS2-VASc',
      fields: [
        { key: 'icc' },
        { key: 'hipertensao' },
        { key: 'diabetes' },
        { key: 'avc_ait_previo' },
        { key: 'tev_previo' },
        { key: 'doenca_vascular' },
      ],
    },
    {
      title: 'HAS-BLED',
      fields: [
        { key: 'hipertensao_nao_controlada' },
        { key: 'funcao_renal_alterada' },
        { key: 'funcao_hepatica_alterada' },
        { key: 'sangramento_previo' },
        { key: 'inr_labil' },
        { key: 'uso_alcool_drogas' },
        { key: 'medicamentos_predisponentes_sangramento' },
      ],
    },
  ],
};

formSpecRegistry['cha2ds2vasc_hasbled'] = spec;
