/**
 * Folha que sobe de baixo — o "modal" da casca mobile.
 *
 * Modal centralizado no celular fica longe do polegar e, com o teclado aberto,
 * metade dele some. A folha nasce onde o dedo já está e cresce até 92% da
 * altura visível, rolando por dentro.
 *
 * Vai por portal para a RAIZ da casca, e não para o `body`: dentro do app da
 * Waid a casca é tudo o que existe, e cobrir a UI do hospedeiro não é nosso
 * papel. E não fica onde foi declarada: aberta de dentro da gaveta, ficaria
 * presa aos 88% de largura dela.
 *
 * Quem abre a folha decide como ela fecha (`onFechar`) — na casca, pelo
 * histórico, para o botão voltar do Android fechar a folha (`camadas.ts`).
 */

import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { Icone } from './Icone';

interface Props {
  titulo?: string;
  onFechar: () => void;
  /** Rodapé fixo (botões), fora da área que rola. */
  rodape?: ReactNode;
  /** Sem ✕ quando a folha exige uma decisão (ex.: consentimento). */
  semFechar?: boolean;
  children: ReactNode;
}

export function BottomSheet({ titulo, onFechar, rodape, semFechar, children }: Props) {
  const idTitulo = useId();
  const folhaRef = useRef<HTMLDivElement>(null);

  // Foco entra na folha e volta para onde estava ao fechar — quem usa leitor
  // de tela não pode ficar perdido atrás do scrim.
  useEffect(() => {
    const antes = document.activeElement as HTMLElement | null;
    folhaRef.current?.focus();
    return () => antes?.focus?.();
  }, []);

  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      if (e.key === 'Escape') onFechar();
    }
    window.addEventListener('keydown', aoTeclar);
    return () => window.removeEventListener('keydown', aoTeclar);
  }, [onFechar]);

  const conteudo = (
    <>
      <div className="mv-scrim" onClick={onFechar} />
      <div
        ref={folhaRef}
        className="mv-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titulo ? idTitulo : undefined}
        tabIndex={-1}
      >
        <div className="mv-handle" aria-hidden="true"><i /></div>
        {titulo && (
          <div className="mv-sheet-h">
            <b id={idTitulo}>{titulo}</b>
            {!semFechar && (
              <button type="button" className="mv-ib" aria-label="Fechar" onClick={onFechar}>
                <Icone n="x" />
              </button>
            )}
          </div>
        )}
        <div className="mv-sheet-b">{children}</div>
        {rodape && <div className="mv-sheet-f">{rodape}</div>}
      </div>
    </>
  );
  const raiz = document.querySelector('.shell-movel');
  return raiz ? createPortal(conteudo, raiz) : conteudo;
}
