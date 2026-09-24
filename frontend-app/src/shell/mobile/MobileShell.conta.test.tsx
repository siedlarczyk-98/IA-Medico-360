/**
 * Conta e perfil na casca mobile.
 *
 * Trava o que tem consequência: o Sair só onde ele faz algo (fora do iframe),
 * o e-mail que não se edita, a especialidade travada que EXPLICA por que está
 * travada, e o salvar que renova o token.
 */
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { renderComProvedores } from '../../test/utils';
import { definirViewport, VIEWPORT_CELULAR } from '../../test/viewport';
import { reiniciarLayout } from '../layout';
import { logout, setToken } from '../../lib/auth';
import { updateProfile } from '../../api/auth';

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
    id: 'user-1', name: 'Ana Beatriz Moura', email: 'ana.moura@hospitalsantaclara.com.br',
    role: 'medico', crm: '123456', crm_state: 'SP', med_status: 'especialista',
    intercom_user_hash: null,
    specialty: 'Clínica médica', specialty_slug: 'clinica-medica', specialty_source: 'cfm', specialty_editavel: false,
  })),
  updateProfile: vi.fn(async () => ({ access_token: 'token-novo' })),
  deleteAccount: vi.fn(),
  listarEspecialidades: vi.fn(async () => []),
}));

vi.mock('../../api/conversations', () => ({
  listConversations: vi.fn(async () => []),
  getConversation: vi.fn(),
}));

vi.mock('../../api/folders', () => ({
  listFolders: vi.fn(async () => []),
  createFolder: vi.fn(), renameFolder: vi.fn(), updateFolder: vi.fn(), deleteFolder: vi.fn(),
  moveConversation: vi.fn(), bulkMoveConversations: vi.fn(),
}));

vi.mock('../../api/usage', () => ({
  getUserUsage: vi.fn(async () => ({ has_limit: true, usage_percentage: 68, week_reset_at: '2026-09-28T12:00:00Z' })),
}));

async function abrirNoCelular({ dentroDaWaid = false } = {}) {
  if (dentroDaWaid) (window as { ReactNativeWebView?: unknown }).ReactNativeWebView = {};
  definirViewport(VIEWPORT_CELULAR);
  reiniciarLayout();
  renderComProvedores(<App />);
  await waitFor(() => expect(document.querySelector('[data-casca="mobile"]')).not.toBeNull());
  return userEvent.setup();
}

const abaConta = () => within(screen.getByRole('navigation', { name: 'Navegação' })).getByRole('button', { name: /conta/i });

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv('VITE_SHELL_MOVEL', 'on');
  window.history.replaceState(null, '', '/');
});

afterEach(() => {
  vi.unstubAllEnvs();
  delete (window as { ReactNativeWebView?: unknown }).ReactNativeWebView;
});

describe('Conta fora da Waid (aba)', () => {
  it('mostra perfil, uso da semana, documentos e Sair', async () => {
    const user = await abrirNoCelular();
    await user.click(abaConta());

    const conta = screen.getByRole('region', { name: 'Conta' });
    expect(await within(conta).findByText('Ana Beatriz Moura')).toBeInTheDocument();
    expect(within(conta).getByText('Clínica médica')).toBeInTheDocument();
    expect(within(conta).getByText('ana.moura@hospitalsantaclara.com.br')).toBeInTheDocument();
    expect(await within(conta).findByText('68%')).toBeInTheDocument();
    expect(within(conta).getByText(/renova .*28\/set/i)).toBeInTheDocument();
    expect(within(conta).getByRole('link', { name: /termos de uso/i })).toHaveAttribute('target', '_blank');
    expect(within(conta).getByRole('link', { name: /política de privacidade/i })).toBeInTheDocument();

    await user.click(within(conta).getByRole('button', { name: 'Sair' }));
    expect(logout).toHaveBeenCalled();
  });

  it('dentro da Waid não há Sair: reabrir a seção autentica de novo', async () => {
    // O logout revoga todos os aparelhos; tocar Sair no app derrubava o chat
    // aberto em outro lugar, e não trocava de conta nenhuma.
    const user = await abrirNoCelular({ dentroDaWaid: true });
    await user.click(screen.getByRole('button', { name: /histórico, pastas e conta/i }));
    await user.click(await screen.findByRole('button', { name: /conta e perfil/i }));

    const conta = screen.getByRole('dialog', { name: 'Conta' });
    expect(await within(conta).findByText('Conectado pela Waid')).toBeInTheDocument();
    expect(within(conta).queryByRole('button', { name: 'Sair' })).toBeNull();
  });

  it('editar perfil: e-mail só leitura, especialidade travada explica por quê, salvar renova o token', async () => {
    const user = await abrirNoCelular();
    await user.click(abaConta());
    await user.click(await screen.findByRole('button', { name: /editar perfil/i }));

    const folha = await screen.findByRole('dialog', { name: 'Editar perfil' });
    expect(await within(folha).findByTestId('perfil-email')).toHaveTextContent('ana.moura@hospitalsantaclara.com.br');
    expect(within(folha).queryByRole('combobox', { name: /especialidade/i })).toBeNull();
    expect(within(folha).getByText(/verificada no conselho federal de medicina/i)).toBeInTheDocument();
    expect(within(folha).getByText('CRM/SP 123456')).toBeInTheDocument();

    const nome = within(folha).getByDisplayValue('Ana Beatriz Moura');
    await user.clear(nome);
    await user.type(nome, 'Ana B. Moura');
    await user.click(within(folha).getByRole('button', { name: 'Salvar' }));

    expect(updateProfile).toHaveBeenCalledWith({ name: 'Ana B. Moura' });
    expect(setToken).toHaveBeenCalledWith('token-novo');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Editar perfil' })).toBeNull());
    // Continua na Conta: salvar fecha a folha, não a tela.
    expect(screen.getByRole('region', { name: 'Conta' })).toBeInTheDocument();
  });
});

describe('Conta dentro da Waid (folha)', () => {
  it('o rodapé da gaveta abre a conta; "Editar perfil" troca a folha, e o voltar fecha', async () => {
    const user = await abrirNoCelular({ dentroDaWaid: true });
    await user.click(screen.getByRole('button', { name: /histórico, pastas e conta/i }));
    await user.click(await screen.findByRole('button', { name: /conta e perfil/i }));

    const conta = screen.getByRole('dialog', { name: 'Conta' });
    expect(await within(conta).findByText('Conectado pela Waid')).toBeInTheDocument();

    await user.click(within(conta).getByRole('button', { name: /editar perfil/i }));
    const perfil = await screen.findByRole('dialog', { name: 'Editar perfil' });
    expect(screen.queryByRole('dialog', { name: 'Conta' })).toBeNull();
    expect(await within(perfil).findByText('Gerenciado pela sua conta Waid.')).toBeInTheDocument();

    act(() => window.history.back());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // A gaveta continua aberta embaixo.
    expect(screen.getByRole('complementary', { name: /histórico e pastas/i })).toBeInTheDocument();
  });
});
