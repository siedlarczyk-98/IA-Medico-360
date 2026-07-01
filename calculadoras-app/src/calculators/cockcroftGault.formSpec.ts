import { formSpecRegistry, type FormSpec } from './formSpecs';

const spec: FormSpec = {
  sections: [
    {
      title: 'Dados do paciente',
      fields: [
        { key: 'idade' },
        { key: 'sexo' },
        { key: 'peso_kg' },
        { key: 'altura_cm' },
        { key: 'creatinina_mgdl' },
        { key: 'tipo_peso' },
      ],
    },
  ],
};

formSpecRegistry['cockcroft_gault'] = spec;
