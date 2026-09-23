import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';
import { instalarMatchMedia } from './viewport';
import { reiniciarRascunho } from '../chat/rascunho';
import { reiniciarLayout } from '../shell/layout';
import { reiniciarCamadas } from '../shell/mobile/camadas';

// jsdom nao implementa a API de scroll. O ChatView rola para o fim a cada
// mensagem enviada, entao sem este stub qualquer teste de chat morre num
// TypeError que nada tem a ver com o que ele verifica.
window.HTMLElement.prototype.scrollIntoView = vi.fn();
window.scrollTo = vi.fn();

// jsdom nao reseta entre arquivos de teste. localStorage carrega preferencia de
// modo e de sidebar (ver MODE_PREFERENCE_KEY / 'sidebarCollapsed'), entao sem a
// limpeza um teste herda o estado do anterior e passa/falha pela ordem.
beforeEach(() => {
  localStorage.clear();
  // Viewport de desktop e `matchMedia` que avalia a consulta. Reinstalado a
  // cada teste pelo mesmo motivo do localStorage: um teste que gira o celular
  // não pode deixar o seguinte em modo mobile. Ver `test/viewport.ts`.
  instalarMatchMedia();
  // A escolha de casca é um store de módulo: recalcula com o viewport acima e
  // relê o override (`?layout=`) — senão herdaria a casca do teste anterior.
  sessionStorage.removeItem('m360_layout');
  reiniciarLayout();
  // O rascunho do campo de pergunta é um store de módulo (sobrevive à troca de
  // casca). Sem isto o texto digitado num teste aparecia no seguinte.
  reiniciarRascunho();
  // Pilha de camadas da casca mobile (gaveta, folhas): também é de módulo.
  reiniciarCamadas();
});

afterEach(() => {
  cleanup();
});
