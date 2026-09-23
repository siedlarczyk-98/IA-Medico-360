/**
 * Escolha de modo e esforço, numa folha.
 *
 * No desktop os seis modos são chips visíveis o tempo todo. No celular eles
 * quebravam em duas linhas (ou rolavam de lado, cortados: "Produt.") e
 * roubavam altura do que importa — a resposta. Aqui o modo vira um chip só no
 * campo de digitação, e a escolha abre esta folha.
 *
 * Sem tempo estimado por esforço, de propósito: a latência medida varia por
 * MODO (raciocínio clínico passa de 30 s no p50, fármacos fica em poucos
 * segundos), e um "~10 s" fixo seria promessa que a tela não cumpre.
 */

import { useState } from 'react';

import type { Effort, OrchestratorMode } from '../../components/InputBar';
import { BottomSheet } from './BottomSheet';
import { Icone } from './Icone';
import { MODOS } from './modos';

interface Props {
  modo: OrchestratorMode;
  esforco: Effort;
  onAplicar: (modo: OrchestratorMode, esforco: Effort) => void;
  onFechar: () => void;
}

const ESFORCOS: { key: Effort; nome: string; detalhe: string }[] = [
  { key: 'rápido', nome: 'Rápido', detalhe: 'Direto ao ponto' },
  { key: 'detalhado', nome: 'Detalhado', detalhe: 'Mais raciocínio e fontes' },
];

export function SheetModo({ modo, esforco, onAplicar, onFechar }: Props) {
  const [modoEscolhido, setModoEscolhido] = useState(modo);
  const [esforcoEscolhido, setEsforcoEscolhido] = useState(esforco);

  return (
    <BottomSheet
      titulo="Modo e esforço"
      onFechar={onFechar}
      rodape={
        <>
          {/* O esforço fica no rodapé fixo, e não depois dos seis modos: ali
              ele caía abaixo da dobra no celular, e quem não rolasse nem
              sabia que a opção existia. */}
          <div className="mv-secao">
            <span className="mv-sec-l" id="mv-esforco">Esforço</span>
            <div className="mv-seg" role="radiogroup" aria-labelledby="mv-esforco">
              {ESFORCOS.map(e => (
                <button
                  key={e.key}
                  type="button"
                  role="radio"
                  aria-checked={e.key === esforcoEscolhido}
                  className={e.key === esforcoEscolhido ? 'on' : undefined}
                  onClick={() => setEsforcoEscolhido(e.key)}
                >
                  {e.nome}<small>{e.detalhe}</small>
                </button>
              ))}
            </div>
          </div>
          <button type="button" className="mv-btn mv-btn-pri mv-full" onClick={() => onAplicar(modoEscolhido, esforcoEscolhido)}>
            Aplicar
          </button>
        </>
      }
    >
      <div className="mv-opts" role="radiogroup" aria-label="Modo">
        {MODOS.map(m => {
          const on = m.key === modoEscolhido;
          return (
            <button
              key={m.key}
              type="button"
              role="radio"
              aria-checked={on}
              className={'mv-opt' + (on ? ' on' : '')}
              onClick={() => setModoEscolhido(m.key)}
            >
              <span className="mv-opt-i"><Icone n={m.icone} s={20} /></span>
              <span className="mv-opt-t"><b>{m.nome}</b><span>{m.descricao}</span></span>
              <span className={'mv-radio' + (on ? ' on' : '')} aria-hidden="true" />
            </button>
          );
        })}
      </div>
    </BottomSheet>
  );
}
