/**
 * Tela inicial da Consulta no celular: saudação no centro e atalhos de modo
 * colados no campo de pergunta.
 *
 * Desenho escolhido pelo Ruben em 23/09/2026 (opção C do canvas "tela vazia
 * no celular", com os ajustes dele). Substituiu as perguntas de exemplo: elas
 * ocupavam a altura toda e ninguém as usava — o médico já sabe o que quer
 * perguntar; o que ele não sabe é que existe um modo para cada tipo de
 * pergunta. Os atalhos mostram isso e trocam o modo com um toque, sem abrir a
 * folha de modo e esforço.
 *
 * Os atalhos ficam EMBAIXO, junto do campo, e não com a saudação: é onde o
 * polegar já está, e com o teclado aberto a saudação some (ver `mobile.css`)
 * mas os atalhos continuam à vista.
 */

import type { ChatController } from '../../chat/useChatController';
import { Icone } from './Icone';
import MedicoLogoAnimada from '../../components/MedicoLogoAnimada';
import { MODOS } from './modos';

function saudacao(nome: string | null | undefined): string {
  const hora = new Date().getHours();
  const periodo = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite';
  return nome ? `${periodo}, ${nome}` : periodo;
}

interface Props {
  chat: ChatController;
  nome?: string | null;
}

export function ConsultaVazia({ chat, nome }: Props) {
  return (
    <div className="mv-vazia">
      <div className="mv-vazia-centro rolagem">
        <MedicoLogoAnimada width={176} className="mv-logo" />
        <h1 className="mv-saudacao">{saudacao(nome)}</h1>
        <p className="mv-lede">Pergunte sobre um caso, fármaco ou exame.</p>
      </div>

      <div className="mv-atalhos">
        <span className="mv-sec-l" id="mv-atalhos-rotulo">Começar por</span>
        <div className="mv-chips rolagem-lateral" role="group" aria-labelledby="mv-atalhos-rotulo">
          {MODOS.map(m => {
            const ativo = chat.selectedMode === m.key;
            return (
              <button
                key={m.key}
                type="button"
                className="mv-chip"
                aria-pressed={ativo}
                title={m.descricao}
                onClick={() => chat.setSelectedMode(m.key)}
              >
                <Icone n={m.icone} s={18} />
                {m.curto}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
