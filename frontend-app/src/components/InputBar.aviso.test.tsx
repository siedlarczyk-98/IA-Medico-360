/**
 * Aviso de extração sem texto (débito #2).
 *
 * Um PDF digitalizado era aceito em silêncio: o médico anexava, enviava,
 * recebia uma resposta pobre e não tinha como saber que o exame nunca chegou
 * ao modelo. O anexo continua sendo aceito — ele pode ter motivo para enviar
 * mesmo assim — mas agora com o aviso visível antes do envio.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InputBar } from './InputBar';
import { extractFile } from '../api/uploads';

vi.mock('../api/uploads', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/uploads')>()),
  extractFile: vi.fn(),
}));

const extractFileMock = vi.mocked(extractFile);
// Texto real devolvido pelo backend (AVISO_PDF_ESCANEADO em
// file_extractor_service.py). Copiado inteiro de propósito: o teste verifica
// que a mensagem diz O QUE FAZER, e uma versão encurtada aqui esconderia
// justamente a parte que importa.
const AVISO =
  'Este PDF parece ser digitalizado: não foi possível ler texto dele. ' +
  'Para que o exame seja analisado, envie a página como imagem (JPG ou PNG) — ' +
  'esse caminho usa leitura visual.';

function arquivo(nome: string) {
  return new File(['conteudo'], nome, { type: 'application/pdf' });
}

const input = () => document.querySelector('input[type="file"]') as HTMLInputElement;

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, 'innerWidth', { value: 1280, writable: true, configurable: true });
});

describe('aviso de extração', () => {
  it('mostra o aviso de forma visível, não só em tooltip', async () => {
    extractFileMock.mockResolvedValue({
      file_id: 'id-1', file_name: 'laudo.pdf', file_type: 'pdf', warning: AVISO,
    });
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('laudo.pdf')]);

    const aviso = await screen.findByTestId('anexo-aviso');
    expect(aviso).toHaveTextContent(/digitalizado/i);
    // Precisa dizer o que fazer, não só que deu errado.
    expect(aviso).toHaveTextContent(/imagem/i);
    // E identificar QUAL arquivo, já que cabem cinco por mensagem.
    expect(aviso).toHaveTextContent('laudo.pdf');
  });

  it('o anexo continua utilizável — o aviso não bloqueia o envio', async () => {
    extractFileMock.mockResolvedValue({
      file_id: 'id-1', file_name: 'laudo.pdf', file_type: 'pdf', warning: AVISO,
    });
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);

    await user.upload(input(), [arquivo('laudo.pdf')]);
    await screen.findByTestId('anexo-aviso');
    await user.click(screen.getByRole('button', { name: /enviar/i }));

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend.mock.calls[0][2]).toHaveLength(1);
  });

  it('não mostra aviso quando a extração deu certo', async () => {
    // Avisar sempre treinaria o médico a ignorar o aviso.
    extractFileMock.mockResolvedValue({
      file_id: 'id-1', file_name: 'laudo.pdf', file_type: 'pdf', warning: null,
    });
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('laudo.pdf')]);

    await screen.findByTestId('anexo-chip');
    expect(screen.queryByTestId('anexo-aviso')).not.toBeInTheDocument();
  });

  it('avisa só sobre o arquivo problemático quando há vários', async () => {
    extractFileMock
      .mockResolvedValueOnce({ file_id: 'id-1', file_name: 'bom.pdf', file_type: 'pdf', warning: null })
      .mockResolvedValueOnce({ file_id: 'id-2', file_name: 'escaneado.pdf', file_type: 'pdf', warning: AVISO });
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('bom.pdf'), arquivo('escaneado.pdf')]);

    const avisos = await screen.findAllByTestId('anexo-aviso');
    expect(avisos).toHaveLength(1);
    expect(avisos[0]).toHaveTextContent('escaneado.pdf');
  });
});
