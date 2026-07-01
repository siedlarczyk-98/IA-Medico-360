import { formSpecRegistry, type FormSpec } from './formSpecs';

const spec: FormSpec = {
  sections: [
    {
      title: 'Critérios CURB-65',
      fields: [
        { key: 'confusao_mental' },
        { key: 'ureia_mgdl' },
        { key: 'fr_irpm' },
        { key: 'pas_mmhg' },
        { key: 'pad_mmhg' },
        { key: 'idade' },
      ],
    },
  ],
};

formSpecRegistry['curb65'] = spec;
