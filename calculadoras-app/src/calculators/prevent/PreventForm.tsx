import { useState } from 'react';
import { Card, CardHeader, Separator, SubHeading, Button, ToggleGroup, Label, InputField, CheckItem } from '../riscoCv/ui';
import { IconTarget } from '../riscoCv/icons';
import { usePreventCalculator } from '../../hooks/usePreventCalculator';
import { AvisosPrevent, PainelPrevent } from './PreventResultPanel';
import { paraExibicao, paraMgdl, rotuloUnidade, type UnidadeLipides } from './preventUnits';

/**
 * Calculadora PREVENT avulsa (AHA, Khan et al. 2024) — a mesma que roda no
 * Step4 do wizard SBC 2025, servida direto, para quem quer só o escore.
 *
 * Diferença deliberada em relação ao passo do wizard: aqui NÃO há classificação
 * SBC (os limiares de 5%/20% sobre o ASCVD de 10 anos, o LDL-c de desempate, os
 * fatores agravantes). Esse branching é da diretriz brasileira, não do PREVENT;
 * exibi-lo fora do fluxograma seria atribuir à AHA uma conduta que ela não
 * recomenda. Esta tela entrega os dez desfechos e os avisos de faixa, como o
 * MDCalc — quem quer a conduta SBC usa a calculadora SBC 2025.
 *
 * Estado local e sem persistência: o endpoint não grava execução nem audit log.
 */

interface Campos {
  sexo: 'M' | 'F';
  idade: string;
  ctMgdl: string;
  hdlMgdl: string;
  sbpMmhg: string;
  bmi: string;
  egfr: string;
  diabetes: boolean;
  fumante: boolean;
  antihtnUse: boolean;
  statinUse: boolean;
}

const INICIAL: Campos = {
  sexo: 'M',
  idade: '',
  ctMgdl: '',
  hdlMgdl: '',
  sbpMmhg: '',
  bmi: '',
  egfr: '',
  diabetes: false,
  fumante: false,
  antihtnUse: false,
  statinUse: false,
};

export function PreventForm() {
  const { mutate: execute, isPending, error, data, reset } = usePreventCalculator();
  const [campos, setCampos] = useState<Campos>(INICIAL);
  const [unidade, setUnidade] = useState<UnidadeLipides>('mgdl');
  const [ctExibido, setCtExibido] = useState('');
  const [hdlExibido, setHdlExibido] = useState('');

  // Qualquer edição invalida o resultado na tela: um número calculado com dados
  // que não são mais os exibidos é pior do que nenhum número.
  const onChange = (patch: Partial<Campos>) => {
    setCampos(prev => ({ ...prev, ...patch }));
    reset();
  };

  const trocarUnidade = (nova: UnidadeLipides) => {
    setUnidade(nova);
    setCtExibido(paraExibicao(campos.ctMgdl, nova));
    setHdlExibido(paraExibicao(campos.hdlMgdl, nova));
  };

  const camposValidos =
    campos.idade !== '' && campos.ctMgdl !== '' && campos.hdlMgdl !== '' &&
    campos.sbpMmhg !== '' && campos.bmi !== '' && campos.egfr !== '';

  const limpar = () => {
    setCampos(INICIAL);
    setCtExibido('');
    setHdlExibido('');
    reset();
  };

  const calcular = () => {
    execute({
      idade: Number(campos.idade),
      sexo: campos.sexo,
      ct_mgdl: Number(campos.ctMgdl),
      hdl_mgdl: Number(campos.hdlMgdl),
      sbp_mmhg: Number(campos.sbpMmhg),
      bmi: Number(campos.bmi),
      egfr: Number(campos.egfr),
      diabetes: campos.diabetes,
      fumante: campos.fumante,
      antihtn_use: campos.antihtnUse,
      statin_use: campos.statinUse,
    });
  };

  // Todos os desfechos fora de faixa: o backend invalida desfecho a desfecho,
  // então isto é o caso extremo (idade fora de 30–79, ou CT/HDL-c/PAS/TFGe fora
  // da faixa do modelo). Sem nenhum número, só os avisos explicam a tela.
  const nadaCalculado =
    data != null &&
    (Object.keys(data) as Array<keyof typeof data>)
      .filter(k => k !== 'avisos')
      .every(k => data[k] == null);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader
          icon={<IconTarget size={18} />}
          title="Escore PREVENT"
          description="AHA, Khan et al. 2024 — modelo base. Risco de eventos cardiovasculares em 10 e 30 anos."
        />

        <SubHeading>Dados do paciente</SubHeading>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <Label>Sexo</Label>
            <ToggleGroup
              value={campos.sexo}
              onChange={v => onChange({ sexo: v })}
              options={[{ value: 'M', label: 'Masculino' }, { value: 'F', label: 'Feminino' }]}
            />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-idade">Idade (anos)</Label>
            <InputField id="prevent-idade" type="number" min={30} max={79} placeholder="30 – 79" value={campos.idade} onChange={v => onChange({ idade: v })} />
          </div>
        </div>

        <Separator />

        <SubHeading>Perfil lipídico e pressórico</SubHeading>
        <div style={{ maxWidth: 240, marginBottom: 14 }}>
          <Label>Unidade do perfil lipídico</Label>
          <ToggleGroup
            value={unidade}
            onChange={v => trocarUnidade(v as UnidadeLipides)}
            options={[{ value: 'mgdl', label: 'mg/dL' }, { value: 'mmoll', label: 'mmol/L' }]}
          />
        </div>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-ct">Colesterol total ({rotuloUnidade(unidade)})</Label>
            <InputField
              id="prevent-ct"
              type="number"
              placeholder={unidade === 'mgdl' ? '130 – 320' : '3,4 – 8,3'}
              value={ctExibido}
              onChange={v => { setCtExibido(v); onChange({ ctMgdl: paraMgdl(v, unidade) }); }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-hdl">HDL-c ({rotuloUnidade(unidade)})</Label>
            <InputField
              id="prevent-hdl"
              type="number"
              placeholder={unidade === 'mgdl' ? '20 – 100' : '0,5 – 2,6'}
              value={hdlExibido}
              onChange={v => { setHdlExibido(v); onChange({ hdlMgdl: paraMgdl(v, unidade) }); }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-sbp">PA sistólica (mmHg)</Label>
            <InputField id="prevent-sbp" type="number" placeholder="90 – 180" value={campos.sbpMmhg} onChange={v => onChange({ sbpMmhg: v })} />
          </div>
        </div>

        <Separator />

        <SubHeading>Antropometria e função renal</SubHeading>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-bmi">IMC (kg/m²)</Label>
            <InputField id="prevent-bmi" type="number" placeholder="18,5 – 39,9" value={campos.bmi} onChange={v => onChange({ bmi: v })} />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-egfr">TFGe (mL/min/1,73m²)</Label>
            <InputField id="prevent-egfr" type="number" placeholder="15 – 140" value={campos.egfr} onChange={v => onChange({ egfr: v })} />
          </div>
        </div>

        <Separator />

        <SubHeading>Fatores clínicos</SubHeading>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <CheckItem checked={campos.diabetes} onChange={v => onChange({ diabetes: v })} label="Diabetes mellitus" />
          <CheckItem checked={campos.fumante} onChange={v => onChange({ fumante: v })} label="Tabagismo atual" />
          <CheckItem checked={campos.antihtnUse} onChange={v => onChange({ antihtnUse: v })} label="Uso de anti-hipertensivo" />
          <CheckItem checked={campos.statinUse} onChange={v => onChange({ statinUse: v })} label="Uso de estatina" />
        </div>

        {data && (
          <div style={{ padding: '14px 16px', borderRadius: 10, background: 'var(--fill2)' }}>
            {nadaCalculado ? (
              <p style={{ fontSize: 13, color: 'var(--pen2)', textAlign: 'center' }}>
                O PREVENT não foi calculado para este paciente.
              </p>
            ) : (
              <PainelPrevent dados={data} />
            )}
            <AvisosPrevent avisos={data.avisos} />
          </div>
        )}

        {error && (
          <p style={{ fontSize: 12.5, color: 'var(--red)' }}>
            Não foi possível calcular o PREVENT. Confira os dados acima.
          </p>
        )}
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="outline" onClick={limpar} disabled={isPending}>
          Limpar
        </Button>
        <Button onClick={calcular} disabled={!camposValidos || isPending}>
          {isPending ? 'Calculando…' : data ? 'Recalcular' : 'Calcular PREVENT'}
        </Button>
      </div>

      <p style={{ fontSize: 11.5, color: 'var(--pen3)', lineHeight: 1.5 }}>
        Khan SS, Matsushita K, Sang Y, et al. Development and Validation of the American Heart
        Association PREVENT Equations. <em>Circulation</em>. 2024;149(6):430–449. Modelo base (sem
        HbA1c, relação albumina/creatinina urinária ou índice de privação social).
      </p>
    </div>
  );
}
