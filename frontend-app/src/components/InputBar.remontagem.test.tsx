/**
 * O campo é remontado quando a casca troca (girar o celular, redimensionar a
 * janela). O que o médico escreveu e o anexo que estava subindo não podem ir
 * junto. Ver `chat/rascunho.ts`.
 */
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InputBar } from './InputBar';
import { extractFile } from '../api/uploads';

vi.mock('../api/uploads', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/uploads')>()),
  extractFile: vi.fn(),
}));

const extractFileMock = vi.mocked(extractFile);
const input = () => document.querySelector('input[type="file"]') as HTMLInputElement;

beforeEach(() => {
  vi.clearAllMocks();
});

describe('InputBar remontado', () => {
  it('mantém o texto digitado e o esforço escolhido', async () => {
    const user = userEvent.setup();
    const primeiro = render(<InputBar onSend={vi.fn()} />);
    await user.type(screen.getByRole('textbox'), 'paciente 82 anos, FA');
    await user.click(screen.getByRole('button', { name: /rápido/i }));

    primeiro.unmount();
    const onSend = vi.fn();
    render(<InputBar onSend={onSend} />);

    expect(screen.getByRole('textbox')).toHaveValue('paciente 82 anos, FA');
    await user.click(screen.getByRole('button', { name: /enviar/i }));
    expect(onSend).toHaveBeenCalledWith('paciente 82 anos, FA', 'rápido', undefined);
  });

  it('o anexo que terminou de subir DEPOIS da remontagem aparece, e segura o envio até lá', async () => {
    const user = userEvent.setup();
    let concluir!: () => void;
    extractFileMock.mockImplementation(
      (f: File) => new Promise(resolve => {
        concluir = () => resolve({ file_id: 'id-1', file_name: f.name, file_type: 'pdf' });
      }),
    );
    const onSend = vi.fn();
    const primeiro = render(<InputBar onSend={onSend} />);
    await user.upload(input(), [new File(['x'], 'laudo-eco.pdf', { type: 'application/pdf' })]);
    await screen.findByText(/processando/i);

    // Troca de casca no meio do upload.
    primeiro.unmount();
    render(<InputBar onSend={onSend} />);

    // Ainda subindo: o novo campo sabe disso e não deixa enviar sem o exame.
    expect(screen.getByText(/processando/i)).toBeInTheDocument();
    await user.type(screen.getByRole('textbox'), 'interprete{Enter}');
    expect(onSend).not.toHaveBeenCalled();

    await act(async () => { concluir(); });

    expect(await screen.findByTestId('anexo-chip')).toHaveTextContent('laudo-eco.pdf');
    await user.click(screen.getByRole('button', { name: /enviar/i }));
    expect(onSend).toHaveBeenCalledWith(
      'interprete', 'detalhado',
      [expect.objectContaining({ fileId: 'id-1', name: 'laudo-eco.pdf' })],
    );
  });

  it('enviar limpa o rascunho para o próximo campo também', async () => {
    const user = userEvent.setup();
    const primeiro = render(<InputBar onSend={vi.fn()} />);
    await user.type(screen.getByRole('textbox'), 'pergunta{Enter}');

    primeiro.unmount();
    render(<InputBar onSend={vi.fn()} />);

    expect(screen.getByRole('textbox')).toHaveValue('');
  });
});
