import { useCompacto } from '../shell/layout';

/**
 * Layout apertado? Segue a casca escolhida em `shell/layout.ts`.
 *
 * Era um `useState` com listener de `resize` próprio (largura ≤ 768). Com duas
 * cascas, uma regra de largura independente discordaria da casca na faixa da
 * histerese — o desktop montado com ajustes de celular, ou o contrário. Com a
 * casca mobile desligada (`VITE_SHELL_MOVEL=off`), a regra antiga continua
 * valendo, lá dentro.
 */
export function useIsMobile(): boolean {
  return useCompacto();
}
