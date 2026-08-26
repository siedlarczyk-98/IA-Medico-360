import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

// jsdom nao reseta entre arquivos de teste. localStorage carrega preferencia de
// modo e de sidebar (ver MODE_PREFERENCE_KEY / 'sidebarCollapsed'), entao sem a
// limpeza um teste herda o estado do anterior e passa/falha pela ordem.
beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});
