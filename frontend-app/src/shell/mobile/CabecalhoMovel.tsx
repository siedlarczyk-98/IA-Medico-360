/**
 * Uma linha de 52 px: ☰ · título · nova consulta (só dentro de uma conversa).
 *
 * Dentro da Waid não há logo: o hospedeiro já mostra a marca logo acima, e
 * repeti-la gastaria a linha mais valiosa da tela. Fora dela (URL direta), a
 * tela vazia mostra a marca no lugar do título.
 */

import { Icone } from './Icone';

interface Props {
  titulo: string;
  subtitulo?: string;
  mostrarMarca: boolean;
  /** Sem ☰ fora da Waid: lá a navegação é pela barra de abas. */
  onMenu?: () => void;
  /**
   * Sem ele, o botão some — é o caso da própria tela de nova consulta, onde
   * tocá-lo abria a mesma tela vazia. Decisão do Ruben (2026-09-25).
   */
  onNova?: () => void;
}

export function CabecalhoMovel({ titulo, subtitulo, mostrarMarca, onMenu, onNova }: Props) {
  return (
    <header className="mv-hdr">
      {onMenu ? (
        <button type="button" className="mv-ib" aria-label="Histórico, pastas e conta" onClick={onMenu}>
          <Icone n="menu" />
        </button>
      ) : <span className="mv-hdr-recuo" aria-hidden="true" />}
      {mostrarMarca ? (
        <div className="mv-marca"><i>M</i>Médico 360</div>
      ) : (
        <div className="mv-hdr-t">
          <b>{titulo}</b>
          {subtitulo && <span>{subtitulo}</span>}
        </div>
      )}
      {/* "+" e não o quadrado com lápis (o "nova conversa" do ChatGPT): na
          homologação ele foi lido como "editar o título". */}
      {onNova && (
        <button type="button" className="mv-ib" aria-label="Nova consulta" onClick={onNova}>
          <Icone n="plus" />
        </button>
      )}
    </header>
  );
}
