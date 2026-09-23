/**
 * Ícones da casca mobile: traço de 1.8 em viewBox 24, pontas arredondadas.
 *
 * Os traçados vêm do protótipo (`design_handoff_medico360_mobile/m360-kit.jsx`).
 * Ficam aqui, sem biblioteca de ícones, porque são poucos e o app não tem
 * nenhuma — uma dependência para duas dúzias de caminhos SVG não se paga.
 */

const TRACOS = {
  plus: 'M12 5v14M5 12h14',
  up: 'M12 19V5M5 12l7-7 7 7',
  clip: 'M20.5 11.5l-8.2 8.2a5 5 0 01-7.1-7.1l8.6-8.6a3.3 3.3 0 014.7 4.7l-8.6 8.6a1.7 1.7 0 01-2.4-2.4l7.9-7.9',
  folder: 'M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z',
  chevR: 'M9 6l6 6-6 6',
  chevD: 'M6 9l6 6 6-6',
  x: 'M6 6l12 12M18 6L6 18',
  check: 'M5 12.5l4.5 4.5L19 7',
  bolt: 'M13 3L5 14h6l-1 7 8-11h-6z',
  steth: 'M6 3v5a4 4 0 008 0V3M10 12v3a5 5 0 0010 0v-2M20 9a2 2 0 110 4 2 2 0 010-4z',
  pill: 'M10.5 3.5a5 5 0 017 7l-7 7a5 5 0 01-7-7zM7 7l10 10',
  tasks: 'M4 6l2 2 3-3M4 13l2 2 3-3M12 7h8M12 14h8M4 19h16',
  scan: 'M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3M8 12h8M8 9h8M8 15h5',
  db: 'M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  alert: 'M12 3.5l9.5 17h-19zM12 10v4.5M12 17.5v.3',
  info: 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 11v5M12 8v.3',
  file: 'M6 3h8l4 4v14H6zM14 3v4h4M9 13h6M9 17h6',
  image: 'M5 5h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2zM8.5 8.5a1.5 1.5 0 110 3 1.5 1.5 0 010-3zM21 15l-5-5-9 9',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  compose: 'M11 4H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-5M17 3l4 4-8 8H9v-4z',
  menu: 'M4 7h16M4 12h16M4 17h16',
  chat: 'M4 6a2 2 0 012-2h12a2 2 0 012 2v9a2 2 0 01-2 2H9l-5 4z',
  clock: 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 7v5l3 2',
  user: 'M12 4a4 4 0 110 8 4 4 0 010-8zM4 21a8 8 0 0116 0',
  chevL: 'M15 6l-6 6 6 6',
  selsq: 'M7 4h10a3 3 0 013 3v10a3 3 0 01-3 3H7a3 3 0 01-3-3V7a3 3 0 013-3zM8 12l3 3 5-6',
  move: 'M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2zM9 13h7M13 10l3 3-3 3',
  edit: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  help: 'M12 3a9 9 0 110 18 9 9 0 010-18zM9.5 9a2.5 2.5 0 015 .5c0 1.5-2.5 2-2.5 3.5M12 17v.3',
  doc: 'M7 3h10a1 1 0 011 1v16a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1zM9 8h6M9 12h6M9 16h4',
  ext: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5',
  logout: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10',
} as const;

export type NomeIcone = keyof typeof TRACOS | 'stop' | 'more';

interface Props {
  n: NomeIcone;
  /** Tamanho em px. */
  s?: number;
  /** Espessura do traço. */
  w?: number;
}

export function Icone({ n, s = 22, w = 1.8 }: Props) {
  if (n === 'stop') {
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" aria-hidden="true">
        <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" />
      </svg>
    );
  }
  if (n === 'more') {
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <circle cx="5" cy="12" r="1.7" /><circle cx="12" cy="12" r="1.7" /><circle cx="19" cy="12" r="1.7" />
      </svg>
    );
  }
  return (
    <svg
      width={s} height={s} viewBox="0 0 24 24" fill="none" aria-hidden="true"
      stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round"
    >
      <path d={TRACOS[n]} />
    </svg>
  );
}
