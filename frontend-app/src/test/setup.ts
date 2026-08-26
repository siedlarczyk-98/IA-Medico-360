import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

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
});

afterEach(() => {
  cleanup();
});
