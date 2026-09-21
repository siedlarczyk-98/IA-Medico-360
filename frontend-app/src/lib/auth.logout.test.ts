/**
 * "Sair" encerra a sessão NO SERVIDOR, não só no navegador.
 *
 * O cookie de sessão é HttpOnly: limpar o localStorage não o alcança, e o token
 * seguia válido por até uma hora. Em estação compartilhada de hospital, o
 * próximo usuário lia o histórico do anterior.
 */
import { descartarSessaoDesteNavegador, getToken, logout, setToken } from './auth';

const fetchMock = vi.fn();

beforeEach(() => {
  localStorage.clear();
  fetchMock.mockReset().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal('fetch', fetchMock);
  // jsdom não navega; basta um `location` gravável para observar o destino.
  Object.defineProperty(window, 'location', { value: { href: '/' }, writable: true, configurable: true });
});

afterEach(() => vi.unstubAllGlobals());

describe('logout', () => {
  it('chama o servidor com o token E com o cookie, e só depois vai para o login', async () => {
    setToken('token-do-medico');

    logout();

    expect(getToken()).toBeNull(); // o token local some na hora
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, opcoes] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/auth\/logout$/);
    expect(opcoes.method).toBe('POST');
    expect(opcoes.credentials).toBe('include'); // sem isto o cookie HttpOnly nem viaja
    expect(opcoes.keepalive).toBe(true);
    expect(opcoes.headers.Authorization).toBe('Bearer token-do-medico');

    await vi.waitFor(() => expect(window.location.href).toBe('/login'));
  });

  it('sair nunca falha: sem rede, ainda limpa e vai para o login', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    setToken('token-do-medico');

    logout();

    await vi.waitFor(() => expect(window.location.href).toBe('/login'));
    expect(getToken()).toBeNull();
  });
});

describe('descartarSessaoDesteNavegador', () => {
  it('apaga token e cookie deste navegador SEM revogar as outras sessões', () => {
    setToken('token-de-quem-usou-antes');

    descartarSessaoDesteNavegador();

    expect(getToken()).toBeNull();
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/auth\/logout\?revogar=false$/);
    expect(window.location.href).toBe('/'); // não redireciona
  });
});
