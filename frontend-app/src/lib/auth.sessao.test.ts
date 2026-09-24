/**
 * 401 no chat leva à reentrada, e não a um balão sem saída (item 60).
 *
 * "Sair" em qualquer aparelho revoga todos (`token_version`). O chat do celular
 * ficava com um token dentro do prazo, recusado em toda chamada, mostrando "Sua
 * sessão expirou. Entre novamente" sem botão nem redirecionamento — por até uma
 * hora, no cenário do evento.
 */

const reservar = vi.fn();
vi.mock('@shared/embed/sessao', () => ({ reservarReentradaPelaWaid: () => reservar() }));

function tokenDe(sub: string): string {
  return `a.${btoa(JSON.stringify({ sub, role: 'medico', exp: 9999999999 }))}.c`;
}

let replace: ReturnType<typeof vi.fn>;

/** Módulo novo a cada teste: `sessaoExpirou` guarda que já está saindo. */
async function carregar() {
  vi.resetModules();
  return import('./auth');
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  reservar.mockReset().mockReturnValue(true);
  replace = vi.fn();
  // jsdom não navega; basta um `location` observável.
  Object.defineProperty(window, 'location', {
    value: { pathname: '/', search: '', replace },
    writable: true,
    configurable: true,
  });
});

describe('sessaoExpirou', () => {
  it('dentro da Waid, vai para o handshake e LIMPA o token', async () => {
    const auth = await carregar();
    auth.setToken(tokenDe('user-1'));

    auth.sessaoExpirou();

    expect(replace).toHaveBeenCalledWith('/embed-auth');
    // Com o token revogado ainda aqui, a EmbedAuthPage devolveria para "/" quando
    // a Waid não respondesse, e as duas telas girariam entre si.
    expect(auth.getToken()).toBeNull();
  });

  it('fora da Waid, ou com a trava de reentrada ativa, vai para o login', async () => {
    reservar.mockReturnValue(false);
    const auth = await carregar();
    auth.setToken(tokenDe('user-1'));

    auth.sessaoExpirou();

    expect(replace).toHaveBeenCalledWith('/login');
  });

  it('vários 401 ao mesmo tempo navegam uma vez só', async () => {
    const auth = await carregar();
    auth.setToken(tokenDe('user-1'));

    auth.sessaoExpirou();
    auth.sessaoExpirou();
    auth.conferirSessao(new Response(null, { status: 401 }));

    expect(replace).toHaveBeenCalledTimes(1);
    expect(reservar).toHaveBeenCalledTimes(1); // a trava de laço não é gasta à toa
  });

  it('não sai da própria tela de entrada', async () => {
    const auth = await carregar();
    window.location.pathname = '/login';

    auth.sessaoExpirou();

    expect(replace).not.toHaveBeenCalled();
  });

  it('conferirSessao só age no 401', async () => {
    const auth = await carregar();
    auth.setToken(tokenDe('user-1'));

    for (const status of [200, 403, 404, 429, 500]) {
      auth.conferirSessao(new Response(null, { status }));
    }

    expect(replace).not.toHaveBeenCalled();
    expect(auth.getToken()).not.toBeNull();
  });
});

describe('retomada depois de entrar de novo', () => {
  it('devolve a pergunta e a conversa ao MESMO médico', async () => {
    const auth = await carregar();
    auth.setToken(tokenDe('user-1'));
    auth.sessaoExpirou({ pergunta: 'dose de amoxicilina', conversaId: 'conv-a' });

    const depois = await carregar();
    depois.setToken(tokenDe('user-1'));

    expect(depois.consumirRetomada()).toEqual({ pergunta: 'dose de amoxicilina', conversaId: 'conv-a' });
    expect(depois.consumirRetomada()).toBeNull(); // consumida
  });

  it('NÃO devolve a pergunta de um médico a outro', async () => {
    // A sessionStorage é da aba. Numa estação compartilhada, quem entra pelo
    // login depois da queda pode ser outra pessoa.
    const auth = await carregar();
    auth.setToken(tokenDe('user-1'));
    auth.sessaoExpirou({ pergunta: 'paciente com HIV, dose de TARV' });

    const depois = await carregar();
    depois.setToken(tokenDe('user-2'));

    expect(depois.consumirRetomada()).toBeNull();
  });

  it('o 401 que chega depois ainda acrescenta à retomada', async () => {
    // A lista e o envio levam 401 juntos; se a lista chegar primeiro, a pergunta
    // não pode se perder por isso.
    const auth = await carregar();
    auth.setToken(tokenDe('user-1'));
    auth.conferirSessao(new Response(null, { status: 401 }));
    auth.sessaoExpirou({ pergunta: 'dose de amoxicilina', conversaId: 'conv-a' });

    const depois = await carregar();
    depois.setToken(tokenDe('user-1'));

    expect(depois.consumirRetomada()).toEqual({ pergunta: 'dose de amoxicilina', conversaId: 'conv-a' });
  });

  it('pergunta em branco não é guardada', async () => {
    const auth = await carregar();
    auth.setToken(tokenDe('user-1'));
    auth.sessaoExpirou({ pergunta: '   ' });

    const depois = await carregar();
    depois.setToken(tokenDe('user-1'));

    expect(depois.consumirRetomada()).toEqual({});
  });
});
