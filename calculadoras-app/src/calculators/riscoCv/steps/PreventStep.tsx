import { useState } from 'react';
import { Card, CardHeader, Separator, SubHeading, Button, ToggleGroup, Label, InputField, CheckItem } from '../ui';
import { IconTarget, IconChevronRight, IconChevronLeft } from '../icons';
import { usePreventCalculator } from '../../../hooks/usePreventCalculator';
import type { PreventAviso, PreventCalculateResponse } from '../../../api/prevent';
import type { RiskLevel } from '../riskTypes';
import type { WizardStepProps } from './types';

/**
 * Única exceção à porta 100% client-side: a referência (`Step4Prevent.tsx`) só
 * linka pro MDCalc e pede o score digitado manualmente. Aqui o escore PREVENT
 * (AHA, Khan et al. 2024) é calculado de verdade num endpoint dedicado
 * (`POST /prevent/calculate`, backend `app/calculators/formulas/cardiologia/
 * prevent.py`) — sem persistir execução/audit log, só para obter o número. O
 * branching a partir do score é idêntico ao da referência.
 */

/**
 * O MDCalc abre o PREVENT em mmol/L com alternador de unidade. Aqui o canônico
 * é mg/dL (o que o backend recebe e o que o laboratório brasileiro reporta); a
 * unidade é só de exibição. Constante idêntica à `mmol_conversion` da AHA.
 */
const MMOL_POR_MGDL = 0.02586;

type UnidadeLipides = 'mgdl' | 'mmoll';

const rotuloUnidade = (u: UnidadeLipides) => (u === 'mgdl' ? 'mg/dL' : 'mmol/L');

/** mg/dL guardado no estado -> string exibida na unidade escolhida. */
const paraExibicao = (mgdl: string, unidade: UnidadeLipides): string => {
  const n = parseFloat(mgdl);
  if (isNaN(n)) return '';
  return unidade === 'mmoll' ? (n * MMOL_POR_MGDL).toFixed(2) : String(n);
};

/** String digitada na unidade escolhida -> mg/dL para o estado. */
const paraMgdl = (digitado: string, unidade: UnidadeLipides): string => {
  if (unidade === 'mgdl') return digitado;
  const n = parseFloat(digitado.replace(',', '.'));
  if (isNaN(n)) return '';
  return (n / MMOL_POR_MGDL).toFixed(1);
};

/**
 * Os cinco desfechos do modelo base. É um superconjunto do MDCalc, que exibe
 * DCV total, ASCVD, coronariana e AVC mas omite insuficiência cardíaca.
 * `—` onde o backend devolveu `null`: a AHA invalida desfecho a desfecho, então
 * é normal a tabela vir parcial (idade > 59 zera a coluna de 30 anos; IMC fora
 * de 18,5–39,9 zera a linha de insuficiência cardíaca).
 */
type CampoPrevent = keyof Omit<PreventCalculateResponse, 'avisos'>;

/**
 * Hierarquia espelhada no MDCalc: o DCV total é o número grande de cada
 * horizonte, os demais desfechos vêm desdobrados abaixo. A diferença é que aqui
 * o ASCVD leva marcação — no MDCalc nenhum número decide nada, enquanto nesta
 * tela é o ASCVD de 10 anos que define a classificação SBC 2025, e o médico
 * precisa saber qual dos cinco puxou a conduta.
 */
const HORIZONTES = [
  {
    rotulo: '10 anos',
    principal: 'cvd_10a' as CampoPrevent,
    linhas: [
      { rotulo: 'Aterosclerótica (ASCVD)', campo: 'ascvd_10a' as CampoPrevent, classifica: true },
      { rotulo: 'Insuficiência cardíaca', campo: 'hf_10a' as CampoPrevent, classifica: false },
      { rotulo: 'Doença coronariana', campo: 'chd_10a' as CampoPrevent, classifica: false },
      { rotulo: 'AVC', campo: 'stroke_10a' as CampoPrevent, classifica: false },
    ],
  },
  {
    rotulo: '30 anos',
    principal: 'cvd_30a' as CampoPrevent,
    linhas: [
      { rotulo: 'Aterosclerótica (ASCVD)', campo: 'ascvd_30a' as CampoPrevent, classifica: false },
      { rotulo: 'Insuficiência cardíaca', campo: 'hf_30a' as CampoPrevent, classifica: false },
      { rotulo: 'Doença coronariana', campo: 'chd_30a' as CampoPrevent, classifica: false },
      { rotulo: 'AVC', campo: 'stroke_30a' as CampoPrevent, classifica: false },
    ],
  },
] as const;

const formata = (v: number | null) => (v == null ? '—' : `${v.toFixed(2)}%`);

function BlocoHorizonte({
  dados,
  horizonte,
}: {
  dados: PreventCalculateResponse;
  horizonte: (typeof HORIZONTES)[number];
}) {
  const { rotulo, principal, linhas } = horizonte;
  // Horizonte inteiro fora de faixa (idade > 59 zera os 30 anos): esconde o
  // bloco e deixa o aviso explicar, em vez de empilhar cinco travessões.
  const vazio = dados[principal] == null && linhas.every(l => dados[l.campo] == null);
  if (vazio) return null;

  return (
    <div style={{ textAlign: 'left' }}>
      <p style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        Risco de DCV total em {rotulo}
      </p>
      <p id={`prevent-${principal}`} style={{ fontSize: 30, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-0.01em', margin: '2px 0 10px' }}>
        {formata(dados[principal])}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {linhas.map(({ rotulo: nome, campo, classifica }) => (
          <div
            key={campo}
            style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12,
              padding: '5px 8px', borderRadius: 6,
              background: classifica ? 'var(--fill1, rgba(0,0,0,0.03))' : 'transparent',
            }}
          >
            <span style={{ fontSize: 12.5, color: 'var(--pen2)' }}>
              {nome}
              {classifica && (
                <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--petrol)', fontWeight: 600 }}>
                  define a classificação SBC
                </span>
              )}
            </span>
            <span
              id={`prevent-${campo}`}
              style={{ fontSize: 13.5, fontWeight: classifica ? 700 : 500, color: 'var(--ink)', whiteSpace: 'nowrap' }}
            >
              {formata(dados[campo])}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PainelPrevent({ dados }: { dados: PreventCalculateResponse }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {HORIZONTES.map(h => (
        <BlocoHorizonte key={h.rotulo} dados={dados} horizonte={h} />
      ))}
    </div>
  );
}

/**
 * Toda célula vazia na tabela precisa vir com o motivo — sem isso o médico não
 * distingue "fora da faixa de validação" de defeito do sistema. As mensagens
 * vêm do backend, da mesma tabela de regras que decide o que não calcular
 * (`app/calculators/formulas/cardiologia/prevent.py`), para as duas não
 * divergirem com o tempo.
 */
function AvisosPrevent({ avisos }: { avisos: PreventAviso[] }) {
  if (avisos.length === 0) return null;
  return (
    <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10, textAlign: 'left' }}>
      {avisos.map(aviso => (
        <p
          key={aviso.codigo}
          style={{
            fontSize: 12.5,
            color: 'var(--pen2)',
            lineHeight: 1.45,
            paddingLeft: 10,
            borderLeft: '2px solid var(--line)',
          }}
        >
          {aviso.mensagem}
        </p>
      ))}
    </div>
  );
}

interface Step4Props extends Omit<WizardStepProps, 'onResult'> {
  onResult: (level: RiskLevel, goToAggravants: boolean) => void;
}

export function PreventStep({ state, onChange, onResult, onBack }: Step4Props) {
  const { mutate: execute, isPending, error, data } = usePreventCalculator();
  const [unidade, setUnidade] = useState<UnidadeLipides>('mgdl');
  const [ctExibido, setCtExibido] = useState(state.ctMgdl);
  const [hdlExibido, setHdlExibido] = useState(state.hdlMgdl);

  const trocarUnidade = (nova: UnidadeLipides) => {
    setUnidade(nova);
    setCtExibido(paraExibicao(state.ctMgdl, nova));
    setHdlExibido(paraExibicao(state.hdlMgdl, nova));
  };

  const clinicalFieldsValid =
    state.idade !== '' && state.ctMgdl !== '' && state.hdlMgdl !== '' &&
    state.sbpMmhg !== '' && state.bmi !== '' && state.egfr !== '';

  const handleCalculate = () => {
    execute(
      {
        idade: Number(state.idade),
        sexo: state.sexo,
        ct_mgdl: Number(state.ctMgdl),
        hdl_mgdl: Number(state.hdlMgdl),
        sbp_mmhg: Number(state.sbpMmhg),
        bmi: Number(state.bmi),
        egfr: Number(state.egfr),
        diabetes: state.hasDM === true,
        fumante: state.fumante,
        antihtn_use: state.antihtnUse,
        statin_use: state.statinUse,
      },
      {
        onSuccess: data => {
          // -1 é um sentinela local: "já calculado, mas o ASCVD não é aplicável".
          // Desde o alinhamento com a AHA o backend invalida desfecho a desfecho,
          // então isso ocorre com idade fora de 30–79, ou CT/HDL-c/PAS/TFGe fora
          // da faixa do modelo. IMC fora de faixa derruba só os desfechos de IC —
          // o ASCVD continua válido. Distinto de `null` = "ainda não calculado".
          onChange({ preventScore: data.ascvd_10a ?? -1 });
        },
      }
    );
  };

  const score = state.preventScore;
  const calculated = score !== null;
  const unavailable = score === -1;
  const ldl = state.ldlMgdl;
  const scoreNum = calculated && !unavailable ? score : NaN;
  const ldlNum = ldl ? parseFloat(ldl) : NaN;
  const needsLdl = !unavailable && !isNaN(scoreNum) && scoreNum < 5;

  const getResultLevel = (): { level: RiskLevel; goToAggravants: boolean } | null => {
    // Sem ASCVD aplicável: segue direto para os fatores agravantes, igual ao
    // fallback do backend quando não há score.
    if (unavailable) return { level: 'low', goToAggravants: true };
    if (isNaN(scoreNum)) return null;
    if (scoreNum >= 20) return { level: 'high', goToAggravants: false };
    if (scoreNum >= 5) return { level: 'intermediate', goToAggravants: true };
    if (isNaN(ldlNum)) return null;
    if (ldlNum >= 190) return null;
    if (ldlNum >= 160) return { level: 'intermediate', goToAggravants: true };
    return { level: 'low', goToAggravants: true };
  };

  const result = getResultLevel();

  const clinicalInputChanged = () => onChange({ preventScore: null });

  const getButtonLabel = () => {
    if (!calculated) return 'Calcular PREVENT';
    if (!result) return 'Informe o LDL-c para continuar';
    if (!result.goToAggravants) return 'Ver Resultado (Alto)';
    return 'Avaliar Agravantes';
  };

  const handleSubmit = () => {
    if (!calculated) {
      handleCalculate();
      return;
    }
    if (!result) return;
    onResult(result.level, result.goToAggravants);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card>
        <CardHeader
          icon={<IconTarget size={18} />}
          title="Escore PREVENT"
          description="Calculado automaticamente (AHA, Khan et al. 2024) a partir dos dados clínicos abaixo."
        />

        <SubHeading>Dados do paciente</SubHeading>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <Label>Sexo</Label>
            <ToggleGroup value={state.sexo} onChange={v => { onChange({ sexo: v }); clinicalInputChanged(); }} options={[{ value: 'M', label: 'Masculino' }, { value: 'F', label: 'Feminino' }]} />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-idade">Idade (anos)</Label>
            <InputField id="prevent-idade" type="number" min={30} max={79} value={state.idade} onChange={v => { onChange({ idade: v }); clinicalInputChanged(); }} />
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
              onChange={v => { setCtExibido(v); onChange({ ctMgdl: paraMgdl(v, unidade) }); clinicalInputChanged(); }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-hdl">HDL-c ({rotuloUnidade(unidade)})</Label>
            <InputField
              id="prevent-hdl"
              type="number"
              placeholder={unidade === 'mgdl' ? '20 – 100' : '0,5 – 2,6'}
              value={hdlExibido}
              onChange={v => { setHdlExibido(v); onChange({ hdlMgdl: paraMgdl(v, unidade) }); clinicalInputChanged(); }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-sbp">PA sistólica (mmHg)</Label>
            <InputField id="prevent-sbp" type="number" value={state.sbpMmhg} onChange={v => { onChange({ sbpMmhg: v }); clinicalInputChanged(); }} />
          </div>
        </div>

        <Separator />

        <SubHeading>Antropometria e função renal</SubHeading>
        <div style={{ display: 'flex', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-bmi">IMC (kg/m²)</Label>
            <InputField id="prevent-bmi" type="number" value={state.bmi} onChange={v => { onChange({ bmi: v }); clinicalInputChanged(); }} />
          </div>
          <div style={{ flex: 1 }}>
            <Label htmlFor="prevent-egfr">TFGe (mL/min/1,73m²)</Label>
            <InputField id="prevent-egfr" type="number" value={state.egfr} onChange={v => { onChange({ egfr: v }); clinicalInputChanged(); }} />
          </div>
        </div>

        <Separator />

        <SubHeading>Fatores clínicos</SubHeading>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <CheckItem checked={state.fumante} onChange={v => { onChange({ fumante: v }); clinicalInputChanged(); }} label="Tabagismo atual" />
          <CheckItem checked={state.antihtnUse} onChange={v => { onChange({ antihtnUse: v }); clinicalInputChanged(); }} label="Uso de anti-hipertensivo" />
          <CheckItem checked={state.statinUse} onChange={v => { onChange({ statinUse: v }); clinicalInputChanged(); }} label="Uso de estatina" />
        </div>

        {calculated && (
          <div style={{ padding: '14px 16px', borderRadius: 10, background: 'var(--fill2)', textAlign: 'center' }}>
            {unavailable ? (
              <>
                <p style={{ fontSize: 13, color: 'var(--pen2)' }}>
                  O PREVENT não foi calculado para este paciente. Segue direto para os fatores
                  agravantes.
                </p>
                {data ? (
                  <AvisosPrevent avisos={data.avisos} />
                ) : (
                  <p style={{ fontSize: 12.5, color: 'var(--pen2)', marginTop: 10 }}>
                    Algum dado está fora da faixa em que o escore foi validado. Recalcule para ver
                    qual.
                  </p>
                )}
              </>
            ) : (
              <>
                {data ? (
                  <>
                    <PainelPrevent dados={data} />
                    <AvisosPrevent avisos={data.avisos} />
                  </>
                ) : (
                  // Sem o payload (ao voltar para o passo), resta o valor que
                  // ficou no estado do wizard — que é o que definiu a conduta.
                  <div style={{ textAlign: 'left' }}>
                    <p style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--pen2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      Risco aterosclerótico em 10 anos
                    </p>
                    <p id="prevent-ascvd_10a" style={{ fontSize: 30, fontWeight: 800, color: 'var(--ink)' }}>
                      {scoreNum.toFixed(2)}%
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {needsLdl && (
          <div>
            <Label htmlFor="prevent-ldl">LDL-c (mg/dL)</Label>
            <InputField id="prevent-ldl" type="number" placeholder="Ex: 145" value={state.ldlMgdl} onChange={v => onChange({ ldlMgdl: v })} />
            <p style={{ fontSize: 12, color: 'var(--pen2)', marginTop: 6 }}>
              Necessário para estratificação quando o risco PREVENT é inferior a 5%.
            </p>
          </div>
        )}

        {error && (
          <p style={{ fontSize: 12.5, color: 'var(--red)' }}>
            Não foi possível calcular o PREVENT. Confira os dados acima.
          </p>
        )}
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="outline" onClick={onBack}>
          <IconChevronLeft size={16} /> Voltar
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={(!calculated && !clinicalFieldsValid) || isPending || (calculated && !result)}
        >
          {isPending ? 'Calculando…' : getButtonLabel()} <IconChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
