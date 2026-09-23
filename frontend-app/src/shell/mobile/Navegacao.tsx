/**
 * Os dois recipientes do Histórico e das Pastas.
 *
 * - `GavetaNavegacao`: dentro da Waid. Abre pelo ☰, da esquerda, com 88% da
 *   largura — sobra uma faixa da conversa à vista, que é o que diz "isto é uma
 *   gaveta, a conversa continua aí atrás". Histórico e Pastas num seletor no
 *   topo; a conta no rodapé.
 * - `BarraDeAbas` + `TelaNavegacao`: fora da Waid. Abas embaixo, e Histórico e
 *   Pastas como telas POR CIMA da Consulta — que nunca é desmontada, para a
 *   resposta em andamento seguir chegando.
 */

import { useState } from 'react';

import type { ChatController } from '../../chat/useChatController';
import type { useConversasEPastas } from '../../hooks/useConversasEPastas';
import { useCurrentUser } from '../../lib/useCurrentUser';
import { useUserUsage } from '../../lib/useUserUsage';
import { voltarPara } from './camadas';
import { Icone, type NomeIcone } from './Icone';
import { iniciais } from './iniciais';
import { PainelNavegacao, type Aba } from './PainelNavegacao';

interface Comum {
  chat: ChatController;
  dados: ReturnType<typeof useConversasEPastas>;
  onIrParaConsulta: () => void;
}

export function GavetaNavegacao({ chat, dados, onIrParaConsulta, onFechar, onConta }: Comum & {
  onFechar: () => void;
  onConta: () => void;
}) {
  const [aba, setAba] = useState<Aba>('historico');
  // Trocar de seção fecha antes o que estiver aberto dentro da gaveta (pasta,
  // seleção): a gaveta é a camada 1, e o seletor volta até ela.
  return (
    <>
      <div className="mv-scrim mv-scrim-gaveta" onClick={onFechar} />
      <aside className="mv-gaveta" aria-label="Histórico e pastas">
        <PainelNavegacao
          aba={aba}
          chat={chat}
          dados={dados}
          onIrParaConsulta={onIrParaConsulta}
          topo={
            <div className="mv-gaveta-topo">
              <div className="mv-gaveta-linha">
                <b>Médico 360</b>
                <button type="button" className="mv-ib" aria-label="Fechar" onClick={onFechar}><Icone n="x" /></button>
              </div>
              <button type="button" className="mv-btn mv-btn-go mv-full" onClick={() => { chat.handleNew(); onIrParaConsulta(); }}>
                <Icone n="plus" w={2.2} />Nova consulta
              </button>
              <div className="mv-seg mv-seg-simples" role="tablist" aria-label="Seção">
                {(['historico', 'pastas'] as const).map(a => (
                  <button key={a} type="button" role="tab" aria-selected={aba === a} className={aba === a ? 'on' : undefined} onClick={() => voltarPara(1, () => setAba(a))}>
                    {a === 'historico' ? 'Histórico' : 'Pastas'}
                  </button>
                ))}
              </div>
            </div>
          }
          rodape={<RodapeConta onConta={onConta} usageTick={chat.usageTick} />}
        />
      </aside>
    </>
  );
}

/** Nome e uso da semana; tocar abre a conta. */
function RodapeConta({ onConta, usageTick }: { onConta: () => void; usageTick: number }) {
  const usuario = useCurrentUser();
  const uso = useUserUsage(usageTick);
  const nome = usuario?.name ?? '';
  return (
    <button type="button" className="mv-gaveta-rodape" onClick={onConta} aria-label="Conta e perfil">
      <span className="mv-avatar" aria-hidden="true">{iniciais(nome)}</span>
      <span className="mv-gaveta-rodape-t">
        <b>{nome || 'Sua conta'}</b>
        {uso.hasLimit && uso.usagePercentage !== null && (
          <>
            <span>{Math.round(uso.usagePercentage)}% do limite semanal</span>
            <span className="mv-barra" aria-hidden="true"><i style={{ width: `${Math.min(100, uso.usagePercentage)}%` }} /></span>
          </>
        )}
      </span>
      <Icone n="chevR" s={20} />
    </button>
  );
}

export type AbaInferior = 'consulta' | Aba | 'conta';

const ABAS: { key: AbaInferior; nome: string; icone: NomeIcone }[] = [
  { key: 'consulta', nome: 'Consulta', icone: 'chat' },
  { key: 'historico', nome: 'Histórico', icone: 'clock' },
  { key: 'pastas', nome: 'Pastas', icone: 'folder' },
  { key: 'conta', nome: 'Conta', icone: 'user' },
];

export function BarraDeAbas({ ativa, respondendo, onAba }: {
  ativa: AbaInferior;
  /** Resposta chegando com o médico em outra aba: ponto verde na Consulta. */
  respondendo: boolean;
  onAba: (a: AbaInferior) => void;
}) {
  return (
    <nav className="mv-abas" aria-label="Navegação">
      {ABAS.map(a => (
        <button
          key={a.key}
          type="button"
          className={'mv-aba' + (ativa === a.key ? ' on' : '')}
          aria-current={ativa === a.key ? 'page' : undefined}
          onClick={() => onAba(a.key)}
        >
          <span className="mv-aba-i"><Icone n={a.icone} /></span>
          {a.nome}
          {a.key === 'consulta' && respondendo && ativa !== 'consulta' && <span className="mv-ponto mv-ponto-aba" aria-label="respondendo" />}
        </button>
      ))}
    </nav>
  );
}

export function TelaNavegacao({ aba, chat, dados, onIrParaConsulta }: Comum & { aba: Aba }) {
  const titulo = aba === 'historico' ? 'Histórico' : 'Pastas';
  return (
    <section className="mv-tela" aria-label={titulo}>
      <PainelNavegacao
        aba={aba}
        chat={chat}
        dados={dados}
        onIrParaConsulta={onIrParaConsulta}
        comBotaoFlutuante
        topo={<h1 className="mv-titulo-grande">{titulo}</h1>}
      />
    </section>
  );
}
