/**
 * A Consulta na casca mobile, com o app inteiro montado num celular.
 *
 * O que a lógica garante já está coberto pelo controller e pelo composer. Aqui
 * se trava o que é DESTA tela: o que aparece dentro e fora da Waid, os atalhos
 * de modo, a folha de modo, o aviso de imagem — que, sem
 * uma tela para ele, deixaria o anexo parado para sempre — e o Parar.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { renderComProvedores, streamComEsperaAntesDoDone, tokensTextDoneEDone } from '../../test/utils';
import { definirViewport, VIEWPORT_CELULAR } from '../../test/viewport';
import { reiniciarLayout } from '../layout';
import { streamQuery, type StreamEvent } from '../../api/orquestrador';
import { extractFile } from '../../api/uploads';

vi.mock('../../lib/auth', () => ({
  sessaoExpirou: vi.fn(), conferirSessao: vi.fn(), consumirRetomada: () => null,
  isAuthenticated: () => true,
  isTokenExpired: () => false,
  getToken: () => 'token-de-teste',
  getTokenPayload: () => ({ sub: 'user-1', exp: 9999999999 }),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  logout: vi.fn(),
}));

vi.mock('../../api/auth', () => ({
  getMe: vi.fn(async () => ({
    id: 'user-1', name: 'Ana Souza', email: 'ana@exemplo.com',
    role: 'medico', crm: null, crm_state: null, med_status: 'especialista',
    intercom_user_hash: null,
  })),
}));

vi.mock('../../api/conversations', () => ({
  listConversations: vi.fn(async () => []),
  getConversation: vi.fn(async () => ({ id: 'conv-1', title: '', feature: 'ORQUESTRADOR', messages: [] })),
}));

vi.mock('../../api/folders', () => ({
  listFolders: vi.fn(async () => []),
  createFolder: vi.fn(), renameFolder: vi.fn(), deleteFolder: vi.fn(),
  moveConversation: vi.fn(), bulkMoveConversations: vi.fn(),
}));

vi.mock('../../api/usage', () => ({
  getUserUsage: vi.fn(async () => ({ has_limit: false, usage_percentage: null, week_reset_at: null })),
}));

vi.mock('../../api/orquestrador', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/orquestrador')>()),
  streamQuery: vi.fn(),
  queryOrquestrador: vi.fn(),
}));

vi.mock('../../api/uploads', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/uploads')>()),
  extractFile: vi.fn(),
}));

const streamQueryMock = vi.mocked(streamQuery);
const extractFileMock = vi.mocked(extractFile);

/** Monta o app num celular em pé, com a casca mobile ligada. */
async function abrirNoCelular() {
  definirViewport(VIEWPORT_CELULAR);
  reiniciarLayout();
  renderComProvedores(<App />);
  await waitFor(() => expect(document.querySelector('[data-casca="mobile"]')).not.toBeNull());
  return userEvent.setup();
}

const campo = () => screen.getByPlaceholderText(/digite sua pergunta/i);

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv('VITE_SHELL_MOVEL', 'on');
  sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllEnvs();
  delete (window as { ReactNativeWebView?: unknown }).ReactNativeWebView;
});

describe('casca mobile — tela vazia', () => {
  it('fora da Waid: marca no cabeçalho, logo, saudação com o nome e os atalhos de modo', async () => {
    await abrirNoCelular();

    expect(screen.getByText('Médico 360')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Médico 360' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: /ana/i })).toBeInTheDocument();
    const atalhos = screen.getByRole('group', { name: /começar por/i });
    expect(within(atalhos).getAllByRole('button')).toHaveLength(6);
    // O modo atual vem marcado.
    expect(within(atalhos).getByRole('button', { name: /busca/i })).toHaveAttribute('aria-pressed', 'true');
  });

  it('dentro do app da Waid: sem marca no cabeçalho, mesma tela vazia', async () => {
    (window as { ReactNativeWebView?: unknown }).ReactNativeWebView = {};
    await abrirNoCelular();

    expect(document.querySelector('[data-hospedeiro]')?.getAttribute('data-hospedeiro')).toBe('hospedado');
    expect(screen.queryByText('Médico 360')).toBeNull();
    expect(screen.getByRole('group', { name: /começar por/i })).toBeInTheDocument();
  });

  it('tocar num atalho troca o modo — sem abrir folha e sem enviar nada', async () => {
    const user = await abrirNoCelular();
    const atalhos = screen.getByRole('group', { name: /começar por/i });

    await user.click(within(atalhos).getByRole('button', { name: /fármacos/i }));

    expect(within(atalhos).getByRole('button', { name: /fármacos/i })).toHaveAttribute('aria-pressed', 'true');
    expect(within(atalhos).getByRole('button', { name: /busca/i })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: /modo: fármacos/i })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(streamQueryMock).not.toHaveBeenCalled();
  });
});

describe('casca mobile — campo de pergunta', () => {
  it('Enter quebra linha no celular; o envio é pelo botão, com modo e esforço escolhidos na folha', async () => {
    streamQueryMock.mockImplementation(() => streamComEsperaAntesDoDone(tokensTextDoneEDone(['ok'])).gerador());
    const user = await abrirNoCelular();

    await user.click(screen.getByRole('button', { name: /trocar modo e esforço/i }));
    const folha = screen.getByRole('dialog', { name: /modo e esforço/i });
    await user.click(within(folha).getByRole('radio', { name: /fármacos/i }));
    await user.click(within(folha).getByRole('radio', { name: /rápido/i }));
    await user.click(within(folha).getByRole('button', { name: /aplicar/i }));
    expect(screen.queryByRole('dialog')).toBeNull();

    await user.type(campo(), 'varfarina{Enter}e amiodarona');
    expect(streamQueryMock).not.toHaveBeenCalled();
    expect(campo()).toHaveValue('varfarina\ne amiodarona');

    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    expect(streamQueryMock).toHaveBeenCalledWith(
      expect.objectContaining({ prompt: 'varfarina\ne amiodarona', mode: 'PHARMA_CHECK', effort: 'rápido' }),
      expect.anything(),
    );
  });

  it('fechar a folha sem aplicar não muda o modo', async () => {
    const user = await abrirNoCelular();
    await user.click(screen.getByRole('button', { name: /trocar modo e esforço/i }));
    await user.click(within(screen.getByRole('dialog')).getByRole('radio', { name: /^exames/i }));
    await user.click(screen.getByRole('button', { name: 'Fechar' }));

    expect(screen.getByRole('button', { name: /modo: busca rápida/i })).toBeInTheDocument();
  });

  it('imagem pede o aviso de dados do paciente antes de subir', async () => {
    extractFileMock.mockResolvedValue({ file_id: 'img-1', file_name: 'ecg.jpg', file_type: 'image' });
    const user = await abrirNoCelular();

    const input = document.querySelector('.shell-movel input[type="file"]') as HTMLInputElement;
    await user.upload(input, [new File(['x'], 'ecg.jpg', { type: 'image/jpeg' })]);

    const aviso = screen.getByRole('dialog', { name: /remova dados do paciente/i });
    expect(within(aviso).getByText(/não passam pelo filtro/i)).toBeInTheDocument();
    expect(extractFileMock).not.toHaveBeenCalled();

    await user.click(within(aviso).getByRole('button', { name: /enviar mesmo assim/i }));
    expect(await screen.findByTestId('anexo-chip')).toHaveTextContent('ecg.jpg');
    expect(extractFileMock).toHaveBeenCalledTimes(1);
  });

  it('durante a resposta o botão vira Parar, e Parar interrompe', async () => {
    // Stream que fica no meio dos tokens até ser abortado.
    let sinal: AbortSignal | undefined;
    streamQueryMock.mockImplementation((_p, s) => {
      sinal = s;
      return (async function* (): AsyncGenerator<StreamEvent> {
        yield { type: 'token', text: 'Apixabana' };
        await new Promise((_r, rej) => s?.addEventListener('abort', () =>
          rej(Object.assign(new Error('abort'), { name: 'AbortError' }))));
      })();
    });
    const user = await abrirNoCelular();

    await user.type(campo(), 'DOAC em FA');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    await waitFor(() => expect(screen.getByTestId('assistant-message')).toHaveTextContent('Apixabana'));
    expect(screen.queryByRole('button', { name: 'Enviar' })).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Parar' }));

    expect(sinal?.aborted).toBe(true);
    expect(await screen.findByRole('button', { name: 'Enviar' })).toBeInTheDocument();
    // O que já tinha chegado fica na tela.
    expect(screen.getByTestId('assistant-message')).toHaveTextContent('Apixabana');
  });

  it('nova consulta pelo cabeçalho limpa a conversa', async () => {
    streamQueryMock.mockImplementation(() => streamComEsperaAntesDoDone(tokensTextDoneEDone(['Resposta.'])).gerador());
    const user = await abrirNoCelular();
    // Na tela vazia o botão não existe: abriria a mesma tela.
    expect(screen.queryByRole('button', { name: 'Nova consulta' })).toBeNull();
    await user.type(campo(), 'pergunta');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    await screen.findByTestId('assistant-message');

    await user.click(screen.getByRole('button', { name: 'Nova consulta' }));

    expect(screen.queryByTestId('assistant-message')).toBeNull();
    expect(await screen.findByRole('heading', { name: /ana/i })).toBeInTheDocument();
  });
});
