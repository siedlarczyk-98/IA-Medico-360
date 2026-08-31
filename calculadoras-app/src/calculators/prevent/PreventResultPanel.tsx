import type { PreventAviso, PreventCalculateResponse } from '../../api/prevent';

/**
 * Apresentação do resultado PREVENT, compartilhada pelas duas entradas da
 * calculadora: o Step4 do wizard SBC 2025 (`riscoCv/steps/PreventStep.tsx`) e a
 * calculadora avulsa (`prevent/PreventForm.tsx`). Vive aqui para as duas não
 * divergirem — a tabela de desfechos e a regra de célula vazia são a parte
 * densa, e duplicá-las é como o número exibido começa a discordar do número
 * calculado.
 *
 * A única diferença entre os dois contextos é `destacarAscvd`: dentro do SBC é
 * o ASCVD de 10 anos que decide a conduta e o médico precisa saber disso; na
 * avulsa nenhum desfecho decide nada, igual ao MDCalc.
 */

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
 * horizonte, os demais desfechos vêm desdobrados abaixo.
 */
const HORIZONTES = [
  {
    rotulo: '10 anos',
    principal: 'cvd_10a' as CampoPrevent,
    linhas: [
      { rotulo: 'Aterosclerótica (ASCVD)', campo: 'ascvd_10a' as CampoPrevent, ascvd10a: true },
      { rotulo: 'Insuficiência cardíaca', campo: 'hf_10a' as CampoPrevent, ascvd10a: false },
      { rotulo: 'Doença coronariana', campo: 'chd_10a' as CampoPrevent, ascvd10a: false },
      { rotulo: 'AVC', campo: 'stroke_10a' as CampoPrevent, ascvd10a: false },
    ],
  },
  {
    rotulo: '30 anos',
    principal: 'cvd_30a' as CampoPrevent,
    linhas: [
      { rotulo: 'Aterosclerótica (ASCVD)', campo: 'ascvd_30a' as CampoPrevent, ascvd10a: false },
      { rotulo: 'Insuficiência cardíaca', campo: 'hf_30a' as CampoPrevent, ascvd10a: false },
      { rotulo: 'Doença coronariana', campo: 'chd_30a' as CampoPrevent, ascvd10a: false },
      { rotulo: 'AVC', campo: 'stroke_30a' as CampoPrevent, ascvd10a: false },
    ],
  },
] as const;

export const formataRisco = (v: number | null) => (v == null ? '—' : `${v.toFixed(2)}%`);

function BlocoHorizonte({
  dados,
  horizonte,
  destacarAscvd,
}: {
  dados: PreventCalculateResponse;
  horizonte: (typeof HORIZONTES)[number];
  destacarAscvd: boolean;
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
        {formataRisco(dados[principal])}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {linhas.map(({ rotulo: nome, campo, ascvd10a }) => {
          const marcado = destacarAscvd && ascvd10a;
          return (
            <div
              key={campo}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12,
                padding: '5px 8px', borderRadius: 6,
                background: marcado ? 'var(--fill1, rgba(0,0,0,0.03))' : 'transparent',
              }}
            >
              <span style={{ fontSize: 12.5, color: 'var(--pen2)' }}>
                {nome}
                {marcado && (
                  <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--petrol)', fontWeight: 600 }}>
                    define a classificação SBC
                  </span>
                )}
              </span>
              <span
                id={`prevent-${campo}`}
                style={{ fontSize: 13.5, fontWeight: marcado ? 700 : 500, color: 'var(--ink)', whiteSpace: 'nowrap' }}
              >
                {formataRisco(dados[campo])}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * `destacarAscvd`: marca o ASCVD de 10 anos como o desfecho que puxa a conduta.
 * Só faz sentido dentro do wizard SBC 2025 — na calculadora avulsa nenhum
 * número decide nada e a marcação seria uma afirmação clínica falsa.
 */
export function PainelPrevent({
  dados,
  destacarAscvd = false,
}: {
  dados: PreventCalculateResponse;
  destacarAscvd?: boolean;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {HORIZONTES.map(h => (
        <BlocoHorizonte key={h.rotulo} dados={dados} horizonte={h} destacarAscvd={destacarAscvd} />
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
export function AvisosPrevent({ avisos }: { avisos: PreventAviso[] }) {
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
