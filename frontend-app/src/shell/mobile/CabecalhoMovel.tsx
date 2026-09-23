/**
 * Uma linha de 52 px: ☰ · título · nova consulta.
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
  onNova: () => void;
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
      <button type="button" className="mv-ib" aria-label="Nova consulta" onClick={onNova}>
        <Icone n="compose" />
      </button>
    </header>
  );
}
