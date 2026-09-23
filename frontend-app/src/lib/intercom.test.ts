/**
 * O balão do Intercom no celular.
 *
 * Medido num print de 375px (23/09/2026): o balão padrão fica no canto inferior
 * direito, em cima do botão Enviar. No telefone ele nasce escondido e o suporte
 * abre pelo menu. Estes testes travam as duas metades — sem a segunda, esconder
 * o balão seria sumir com o suporte.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

function simularTela(telefone: boolean) {
  vi.stubGlobal('matchMedia', vi.fn((q: string) => ({
    matches: telefone && q.includes('max-width'),
    media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
}

async function carregarModulo() {
  vi.resetModules();
  return import('./intercom');
}

beforeEach(() => {
  delete window.Intercom;
  delete window.intercomSettings;
  // O snippet insere o widget antes do primeiro <script> da página. Numa página
  // do Vite sempre há um; no jsdom, não.
  if (!document.querySelector('script')) document.head.appendChild(document.createElement('script'));
});

afterEach(() => vi.unstubAllGlobals());

describe('balão do Intercom', () => {
  it('nasce escondido no telefone', async () => {
    simularTela(true);
    const { loadIntercom } = await carregarModulo();

    loadIntercom('app-teste');

    expect(window.intercomSettings?.hide_default_launcher).toBe(true);
  });

  it('continua visível no desktop', async () => {
    simularTela(false);
    const { loadIntercom } = await carregarModulo();

    loadIntercom('app-teste');

    expect(window.intercomSettings?.hide_default_launcher).toBe(false);
  });
});

describe('suporte pelo menu', () => {
  it('só se oferece quando o widget foi carregado', async () => {
    simularTela(true);
    const { loadIntercom, suporteDisponivel } = await carregarModulo();

    expect(suporteDisponivel()).toBe(false);
    loadIntercom('app-teste');
    expect(suporteDisponivel()).toBe(true);
  });

  it('abre o Messenger', async () => {
    const { abrirSuporte } = await carregarModulo();
    const intercom = vi.fn();
    window.Intercom = intercom as unknown as typeof window.Intercom;

    abrirSuporte();

    expect(intercom).toHaveBeenCalledWith('show');
  });
});
