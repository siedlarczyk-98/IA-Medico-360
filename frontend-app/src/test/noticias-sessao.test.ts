/**
 * Sessão das NOTÍCIAS quando cai (item 68 de `docs/pitacos-do-fable-2.md`).
 *
 * Mora aqui porque o `noticias-app` não tem runner de teste unitário; este é o
 * vitest mais próximo, e o módulo testado não depende de nada deste app além do
 * `@shared`, que os dois resolvem igual.
 *
 * Os dois defeitos:
 *  1. a trava contra laço da reentrada pela Waid só limpava o token e parava:
 *     o app ficava na mesma tela, sem sessão, cada toque recusado, sem login;
 *  2. todo 401 recarrega, e quem editava os temas voltava ao feed sem as
 *     marcações.
 */

const hospedado = vi.fn();
const reservar = vi.fn();
vi.mock('@shared/embed/sessao', () => ({
  hospedadoNaWaid: () => hospedado(),
  reservarReentradaPelaWaid: () => reservar(),
}));
const aberto = vi.fn();
const guardar = vi.fn();
vi.mock('@shared/embed/formulario', () => ({
  formularioAberto: (chave: string) => aberto(chave),
  guardarFormulariosAbertos: (dono: unknown) => guardar(dono),
}));

function tokenDe(sub: string): string {
  return `a.${btoa(JSON.stringify({ sub, role: 'medico', exp: 9999999999 }))}.c`;
}

let reload: ReturnType<typeof vi.fn>;
let replaceState: ReturnType<typeof vi.spyOn>;

/** Módulo novo a cada teste: `sessaoExpirou` guarda que já está saindo. */
async function carregar() {
  vi.resetModules();
  return import('../../../noticias-app/src/lib/auth');
}

beforeEach(() => {
  localStorage.clear();
  hospedado.mockReset().mockReturnValue(true);
  reservar.mockReset().mockReturnValue(true);
  aberto.mockReset().mockReturnValue(false);
  guardar.mockReset();
  reload = vi.fn();
  replaceState = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {});
  Object.defineProperty(window, 'location', {
    value: { pathname: '/', reload },
    writable: true,
    configurable: true,
  });
});

afterEach(() => vi.restoreAllMocks());

it('com a trava de reentrada ativa, vai para a tela de código em vez de ficar mudo', async () => {
  reservar.mockReturnValue(false);
  const auth = await carregar();
  const mostrarLogin = vi.fn();
  auth.aoPrecisarDeLogin(mostrarLogin);
  auth.setToken(tokenDe('medico-1'));

  auth.sessaoExpirou();

  expect(mostrarLogin).toHaveBeenCalledTimes(1);
  expect(reload).not.toHaveBeenCalled();
  expect(auth.getToken()).toBeNull();
});

it('sem trava, recarrega para refazer a entrada pela Waid', async () => {
  const auth = await carregar();
  const mostrarLogin = vi.fn();
  auth.aoPrecisarDeLogin(mostrarLogin);
  auth.setToken(tokenDe('medico-1'));

  auth.sessaoExpirou();

  expect(reload).toHaveBeenCalledTimes(1);
  expect(mostrarLogin).not.toHaveBeenCalled();
});

it('guarda o que estava aberto em nome do médico que caiu, antes de recarregar', async () => {
  const auth = await carregar();
  auth.setToken(tokenDe('medico-1'));

  auth.sessaoExpirou();

  expect(guardar).toHaveBeenCalledWith('medico-1');
});

it('editando os temas, a volta reabre a tela de temas', async () => {
  aberto.mockImplementation((chave: string) => chave === 'temas');
  const auth = await carregar();
  auth.setToken(tokenDe('medico-1'));

  auth.sessaoExpirou();

  expect(replaceState).toHaveBeenCalledWith(null, '', '/preferencias');
  expect(reload).toHaveBeenCalled();
});

it('fora dos temas, a URL fica como está (um /artigo aberto volta aberto)', async () => {
  window.location.pathname = '/artigo/153';
  const auth = await carregar();
  auth.setToken(tokenDe('medico-1'));

  auth.sessaoExpirou();

  expect(replaceState).not.toHaveBeenCalled();
});
