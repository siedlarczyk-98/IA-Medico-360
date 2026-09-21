/**
 * Regressão do bug de resposta picotada.
 *
 * Sintoma relatado: a resposta começava, cortava, e recomeçava num balão novo —
 * em conversas longas até ~5 vezes. O fragmento ficava congelado e sem badge de
 * modo; só o último balão recebia o badge.
 *
 * Causa: `assistantIndex` era atribuído DENTRO do updater do `setMessages`, que
 * o React não executa de forma síncrona. Um segundo `token` chegando antes de a
 * atualização ser aplicada ainda via `-1` e criava outra mensagem.
 *
 * Estes testes alimentam vários `token` sem ceder o event loop entre eles, que é
 * exatamente a condição da corrida.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { renderComProvedores, streamComEsperaAntesDoDone, streamEmLote, tokensEDone, tokensTextDoneEDone } from './test/utils';
import { streamQuery } from './api/orquestrador';
import { ErroDeApi } from './api/erros';

vi.mock('./lib/auth', () => ({
  isAuthenticated: () => true,
  isTokenExpired: () => false,
  getToken: () => 'token-de-teste',
  getTokenPayload: () => ({ sub: 'user-1', exp: 9999999999 }),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  logout: vi.fn(),
}));

vi.mock('./api/auth', () => ({
  getMe: vi.fn(async () => ({
    id: 'user-1', name: 'Ana Souza', email: 'ana@exemplo.com',
    role: 'medico', crm: null, crm_state: null, med_status: 'especialista',
    intercom_user_hash: null,
  })),
}));

vi.mock('./api/conversations', () => ({
  listConversations: vi.fn(async () => []),
  getConversation: vi.fn(async () => ({ id: 'conv-1', title: '', feature: 'ORQUESTRADOR', messages: [] })),
}));

vi.mock('./api/folders', () => ({
  listFolders: vi.fn(async () => []),
  createFolder: vi.fn(), renameFolder: vi.fn(), deleteFolder: vi.fn(),
  moveConversation: vi.fn(), bulkMoveConversations: vi.fn(),
}));

vi.mock('./api/usage', () => ({
  getUserUsage: vi.fn(async () => ({ has_limit: false, usage_percentage: null, week_reset_at: null })),
}));

vi.mock('./api/orquestrador', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api/orquestrador')>()),
  streamQuery: vi.fn(),
  queryOrquestrador: vi.fn(),
}));

const streamQueryMock = vi.mocked(streamQuery);

/** Digita no campo e envia, devolvendo o controle só depois do envio. */
async function enviarPergunta(texto = 'monte uma anamnese') {
  const user = userEvent.setup();
  const campo = await screen.findByPlaceholderText(/digite sua pergunta/i);
  await user.type(campo, texto);
  await user.click(screen.getByRole('button', { name: /enviar/i }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('streaming do orquestrador', () => {
  it('produz UMA mensagem quando os tokens chegam todos no mesmo lote', async () => {
    streamQueryMock.mockImplementation(() =>
      streamEmLote(tokensEDone(['Segue um', ' modelo', ' organizado', ' de anamnese.'])),
    );

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toBeInTheDocument();
    });

    // O coração da regressão: antes da correção saíam vários balões.
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
  });

  it('mantém a resposta inteira, sem perder o prefixo num fragmento', async () => {
    streamQueryMock.mockImplementation(() =>
      streamEmLote(tokensEDone(['Segue um', ' modelo', ' organizado', ' de anamnese.'])),
    );

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent(
        'Segue um modelo organizado de anamnese.',
      );
    });
  });

  it('aplica o badge de modo na mensagem que recebeu os tokens', async () => {
    // No print do bug, o fragmento saía SEM badge e só o último balão tinha.
    streamQueryMock.mockImplementation(() =>
      streamEmLote(tokensEDone(['Segue um', ' modelo'], { mode: 'PRODUCTIVITY' })),
    );

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent(/produtividade/i);
    });
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
  });

  it('não duplica mesmo com muitos tokens no mesmo lote', async () => {
    // 200 tokens: com o bug, cada token que perdia a corrida virava um balão.
    const muitos = Array.from({ length: 200 }, (_, i) => `t${i} `);
    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(muitos)));

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
    expect(screen.getByTestId('assistant-message')).toHaveTextContent('t199');
  });

  it('a pergunta do médico aparece uma vez só', async () => {
    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['ok'])));

    renderComProvedores(<App />);
    await enviarPergunta('monte uma anamnese');

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('user-message')).toHaveLength(1);
  });

  // ── text_done: digitação liberada antes dos metadados ──────────────────
  // O `done` do backend só sai depois do PubMed. Enquanto o input dependia
  // dele, a resposta ficava inteira na tela com o campo bloqueado — que é o
  // momento em que o produto parecia travado.

  it('libera a digitação no text_done, sem esperar o done', async () => {
    const { gerador, liberar } = streamComEsperaAntesDoDone(
      tokensTextDoneEDone(['Segue um', ' modelo de anamnese.']),
    );
    streamQueryMock.mockImplementation(() => gerador());

    renderComProvedores(<App />);
    await enviarPergunta();

    // Texto completo na tela...
    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent(
        'Segue um modelo de anamnese.',
      );
    });

    // ...e o ENVIO já está liberado, com o `done` ainda pendente. (O campo em si
    // nunca é desabilitado; o que o `text_done` libera é o botão, que deixa de
    // ser "Parar" e volta a ser "Enviar".)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /enviar/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /parar/i })).not.toBeInTheDocument();

    liberar();
  });

  it('avisa que as referências ainda estão vindo durante a espera', async () => {
    const { gerador, liberar } = streamComEsperaAntesDoDone(
      tokensTextDoneEDone(['resposta pronta']),
    );
    streamQueryMock.mockImplementation(() => gerador());

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByText(/verificando referências/i)).toBeInTheDocument();
    });

    liberar();

    // E some quando o `done` chega.
    await waitFor(() => {
      expect(screen.queryByText(/verificando referências/i)).not.toBeInTheDocument();
    });
  });

  it('fixa a conversa no text_done, para a próxima pergunta não abrir outra', async () => {
    // Sem o conversation_id no text_done, a pergunta enviada durante a espera
    // iria sem conversa e o backend abriria uma nova.
    streamQueryMock.mockImplementation(() =>
      streamEmLote(tokensTextDoneEDone(['primeira resposta'])),
    );

    renderComProvedores(<App />);
    await enviarPergunta('primeira pergunta');
    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent('primeira resposta');
    });

    streamQueryMock.mockImplementation(() =>
      streamEmLote(tokensTextDoneEDone(['segunda resposta'])),
    );
    await enviarPergunta('segunda pergunta');

    await waitFor(() => {
      expect(screen.getAllByTestId('assistant-message')).toHaveLength(2);
    });
    expect(streamQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ conversation_id: 'conv-1' }),
      expect.anything(),
    );
  });

  it('uma segunda pergunta não apaga a resposta da primeira', async () => {
    // A limpeza de stream abortado truncava a lista a partir de um índice
    // guardado. Com o id, ela remove só a mensagem parcial correspondente.
    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['primeira resposta'])));

    renderComProvedores(<App />);
    await enviarPergunta('primeira pergunta');
    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent('primeira resposta');
    });

    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['segunda resposta'])));
    await enviarPergunta('segunda pergunta');

    await waitFor(() => {
      expect(screen.getAllByTestId('assistant-message')).toHaveLength(2);
    });
    const respostas = screen.getAllByTestId('assistant-message');
    expect(respostas[0]).toHaveTextContent('primeira resposta');
    expect(respostas[1]).toHaveTextContent('segunda resposta');
  });

  it('pergunta enviada ENTRE o text_done e o done não apaga a resposta anterior', async () => {
    // O teste acima só cobre o primeiro stream já encerrado. O defeito real
    // morava no intervalo: o `text_done` libera o campo, mas a marcação de
    // "mensagem em streaming" só era limpa no `finally`, depois do `done`. Uma
    // pergunta nessa janela — enquanto as referências são verificadas, que é
    // quando o médico já leu e quer seguir — tratava a resposta CONCLUÍDA como
    // parcial de um stream abortado e a removia da tela.
    const primeiro = streamComEsperaAntesDoDone(tokensTextDoneEDone(['primeira resposta']));
    streamQueryMock.mockImplementation(() => primeiro.gerador());

    renderComProvedores(<App />);
    await enviarPergunta('primeira pergunta');
    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent('primeira resposta');
    });
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/digite sua pergunta/i)).not.toBeDisabled();
    });

    // O `done` da primeira AINDA não chegou.
    streamQueryMock.mockImplementation(() => streamEmLote(tokensTextDoneEDone(['segunda resposta'])));
    await enviarPergunta('segunda pergunta');

    await waitFor(() => {
      expect(screen.getAllByTestId('assistant-message')).toHaveLength(2);
    });
    const respostas = screen.getAllByTestId('assistant-message');
    expect(respostas[0]).toHaveTextContent('primeira resposta');
    expect(respostas[1]).toHaveTextContent('segunda resposta');

    primeiro.liberar();
  });

  it('cota semanal esgotada aparece como cota, não como queda do servidor', async () => {
    const limite = 'Limite semanal de uso atingido. Seu limite será reiniciado em 7 dias a partir da sua primeira interação.';
    streamQueryMock.mockImplementation(() => {
      throw new ErroDeApi(429, limite);
    });

    renderComProvedores(<App />);
    await enviarPergunta();

    expect(await screen.findByText(new RegExp('Limite semanal de uso atingido'))).toBeInTheDocument();
    expect(screen.queryByText(/erro ao conectar/i)).not.toBeInTheDocument();
  });

  it('queda de rede continua dizendo que não conectou', async () => {
    streamQueryMock.mockImplementation(() => {
      throw new TypeError('Failed to fetch');
    });

    renderComProvedores(<App />);
    await enviarPergunta();

    expect(await screen.findByText(/erro ao conectar com o servidor/i)).toBeInTheDocument();
  });

  // ── Durante a resposta: campo livre, e "Parar" no lugar de "Enviar" ─────────
  // O campo ficava bloqueado de 13 a 57 s: o médico não rascunhava a próxima
  // pergunta, não cancelava uma errada, e perdia o foco do teclado.

  it('o médico digita a próxima pergunta enquanto a resposta chega', async () => {
    const { gerador, liberar } = streamComEsperaAntesDoDone(tokensEDone(['resposta em andamento']));
    streamQueryMock.mockImplementation(() => gerador());

    renderComProvedores(<App />);
    const user = await enviarPergunta('primeira pergunta');
    await screen.findByText('resposta em andamento');

    const campo = screen.getByPlaceholderText(/digite sua pergunta/i);
    expect(campo).not.toBeDisabled();
    await user.type(campo, 'rascunho da próxima');
    expect(campo).toHaveValue('rascunho da próxima');

    liberar();
  });

  it('Enter durante a resposta não dispara outra pergunta', async () => {
    const { gerador, liberar } = streamComEsperaAntesDoDone(tokensEDone(['resposta em andamento']));
    streamQueryMock.mockImplementation(() => gerador());

    renderComProvedores(<App />);
    const user = await enviarPergunta('primeira pergunta');
    await screen.findByText('resposta em andamento');

    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), 'segunda{Enter}');

    expect(streamQueryMock).toHaveBeenCalledTimes(1);
    liberar();
  });

  it('"Parar" cancela a resposta e mantém na tela o que já chegou', async () => {
    const { gerador, liberar } = streamComEsperaAntesDoDone(tokensEDone(['texto parcial']));
    streamQueryMock.mockImplementation(() => gerador());

    renderComProvedores(<App />);
    const user = await enviarPergunta('pergunta errada');
    await screen.findByText('texto parcial');

    await user.click(screen.getByRole('button', { name: /parar/i }));

    const sinal = streamQueryMock.mock.calls[0][1] as AbortSignal;
    expect(sinal.aborted).toBe(true);
    expect(screen.getByText('texto parcial')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /enviar/i })).toBeInTheDocument();

    liberar();
  });
});
