/**
 * Tela inicial da Consulta no celular: saudação e sugestões tocáveis.
 *
 * O desktop mostra seis cartões grandes de modo. No celular, dentro do site da
 * Waid, esses cartões ocupavam a área inteira do iframe (~2/3 da tela) e
 * empurravam o campo de pergunta para baixo da dobra. Aqui o bloco fica
 * ALINHADO AO FUNDO, colado no campo, e as sugestões são perguntas de verdade:
 * mostram o que dá para pedir melhor do que um nome de modo.
 *
 * Tocar numa sugestão PREENCHE o campo (e ajusta o modo) — não envia. O médico
 * quase sempre quer trocar um detalhe antes, e uma pergunta enviada por engano
 * custa uma resposta inteira.
 */

import type { OrchestratorMode } from '../../components/InputBar';
import type { ChatController } from '../../chat/useChatController';
import { alterarRascunho } from '../../chat/rascunho';
import { Icone } from './Icone';
import { modo } from './modos';

const SUGESTOES: { texto: string; modo: OrchestratorMode }[] = [
  { texto: 'Dor torácica em jovem com ECG normal: o que investigar?', modo: 'CLINICAL_REASONING' },
  { texto: 'Interação entre claritromicina e sinvastatina', modo: 'PHARMA_CHECK' },
  { texto: 'Dose de amoxicilina para otite média em criança de 15 kg', modo: 'QUICK_SEARCH' },
  { texto: 'Resumo de alta para ICC descompensada', modo: 'PRODUCTIVITY' },
];

function saudacao(nome: string | null | undefined): string {
  const hora = new Date().getHours();
  const periodo = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite';
  return nome ? `${periodo}, ${nome}` : periodo;
}

interface Props {
  chat: ChatController;
  nome?: string | null;
  /**
   * Dentro da Waid a altura útil é menor (cabeçalho e abas do hospedeiro em
   * volta): três sugestões e saudação menor, para o campo não sair da tela.
   */
  compacta: boolean;
}

export function ConsultaVazia({ chat, nome, compacta }: Props) {
  const sugestoes = compacta ? SUGESTOES.slice(0, 3) : SUGESTOES;
  return (
    <div className="mv-vazia rolagem">
      <div className="mv-vazia-bloco">
        <h1 className={'mv-saudacao' + (compacta ? ' compacta' : '')}>{saudacao(nome)}</h1>
        {!compacta && <p className="mv-lede">Pergunte sobre um caso, fármaco ou exame.</p>}
        <div className="mv-sugs">
          {sugestoes.map(s => (
            <button
              key={s.texto}
              type="button"
              className="mv-sug"
              onClick={() => {
                chat.setSelectedMode(s.modo);
                alterarRascunho({ texto: s.texto });
              }}
            >
              <span className="mv-sug-i"><Icone n={modo(s.modo).icone} s={18} /></span>
              {s.texto}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
