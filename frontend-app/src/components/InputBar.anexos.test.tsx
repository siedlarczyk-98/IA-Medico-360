/**
 * Vários anexos por mensagem (Fase 5 / item 6).
 *
 * Antes cabia um arquivo só: anexar o segundo substituía o primeiro em
 * silêncio. Discutir um caso costuma exigir laudo + imagem + laboratorial
 * juntos, e o modelo precisa vê-los na mesma mensagem para compará-los.
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

function arquivo(nome: string, tipo = 'application/pdf', bytes = 1000) {
  const f = new File(['x'.repeat(bytes)], nome, { type: tipo });
  return f;
}

/** O consentimento de imagem é pedido 1x por sessão; aceita de antemão. */
function aceitarConsentimentoDeImagem() {
  sessionStorage.setItem('img_dlp_ack', '1');
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  Object.defineProperty(window, 'innerWidth', { value: 1280, writable: true, configurable: true });
  let n = 0;
  extractFileMock.mockImplementation(async (f: File) => {
    n += 1;
    return { file_id: `id-${n}`, file_name: f.name, file_type: f.type.startsWith('image/') ? 'image' : 'pdf' };
  });
});

const input = () => document.querySelector('input[type="file"]') as HTMLInputElement;

describe('InputBar com vários anexos', () => {
  // ── Anexo perdido (varredura de 2026-09-18, item 12) ─────────────────────
  // A resposta clínica saía SEM o exame, e o médico não ficava sabendo.

  it('Enter durante a extração NÃO envia a mensagem sem o exame', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    let concluir!: () => void;
    extractFileMock.mockImplementation(
      (f: File) => new Promise(resolve => {
        concluir = () => resolve({ file_id: 'id-1', file_name: f.name, file_type: 'pdf' });
      }),
    );
    render(<InputBar onSend={onSend} />);

    await user.upload(input(), [arquivo('hemograma.pdf')]);
    await screen.findByText(/processando/i);
    await user.type(screen.getByRole('textbox'), 'interprete este exame{Enter}');

    // Extração ainda em andamento: nada pode ter saído.
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /enviar/i })).toBeDisabled();

    concluir();
    await screen.findByTestId('anexo-chip');
    await user.click(screen.getByRole('button', { name: /enviar/i }));

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend.mock.calls[0][2]).toEqual([expect.objectContaining({ name: 'hemograma.pdf' })]);
  });

  it('um arquivo com erro não descarta os que já foram processados', async () => {
    const user = userEvent.setup();
    extractFileMock.mockImplementation(async (f: File) => {
      if (f.name === 'corrompido.pdf') throw new Error('Não foi possível ler o arquivo.');
      return { file_id: `id-${f.name}`, file_name: f.name, file_type: 'pdf' };
    });
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('laudo.pdf'), arquivo('corrompido.pdf'), arquivo('ecg.pdf')]);

    // Os dois bons ficam; o ruim é nomeado no erro.
    expect(await screen.findAllByTestId('anexo-chip')).toHaveLength(2);
    expect(screen.getByText('laudo.pdf')).toBeInTheDocument();
    expect(screen.getByText('ecg.pdf')).toBeInTheDocument();
    expect(screen.getByText(/corrompido\.pdf/)).toBeInTheDocument();
  });

  it('aceita mais de um arquivo na mesma mensagem', async () => {
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('laudo.pdf'), arquivo('hemograma.docx')]);

    expect(await screen.findAllByTestId('anexo-chip')).toHaveLength(2);
  });

  it('o segundo anexo não substitui o primeiro', async () => {
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('primeiro.pdf')]);
    await screen.findByText('primeiro.pdf');
    await user.upload(input(), [arquivo('segundo.pdf')]);

    expect(await screen.findByText('primeiro.pdf')).toBeInTheDocument();
    expect(screen.getByText('segundo.pdf')).toBeInTheDocument();
  });

  it('envia todos os anexos juntos', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);

    await user.upload(input(), [arquivo('a.pdf'), arquivo('b.pdf')]);
    await screen.findAllByTestId('anexo-chip');
    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), 'compare');
    await user.click(screen.getByRole('button', { name: /enviar/i }));

    const anexos = onSend.mock.calls[0][2];
    expect(anexos).toHaveLength(2);
    expect(anexos.map((a: { name: string }) => a.name)).toEqual(['a.pdf', 'b.pdf']);
  });

  it('remove um anexo sem derrubar os outros', async () => {
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('fica.pdf'), arquivo('sai.pdf')]);
    await screen.findByText('sai.pdf');

    await user.click(screen.getByRole('button', { name: /remover sai\.pdf/i }));

    expect(screen.queryByText('sai.pdf')).not.toBeInTheDocument();
    expect(screen.getByText('fica.pdf')).toBeInTheDocument();
  });

  it('recusa acima do teto de 5 antes de subir qualquer coisa', async () => {
    // Avisar antes do upload evita gastar chamada de visão para receber 422.
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), Array.from({ length: 6 }, (_, i) => arquivo(`f${i}.pdf`)));

    expect(await screen.findByText(/máximo de 5 arquivos/i)).toBeInTheDocument();
    expect(extractFileMock).not.toHaveBeenCalled();
  });

  it('permite enviar só anexo, sem texto', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);

    await user.upload(input(), [arquivo('exame.pdf')]);
    await screen.findByTestId('anexo-chip');
    await user.click(screen.getByRole('button', { name: /enviar/i }));

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('limpa os anexos depois do envio', async () => {
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('exame.pdf')]);
    await screen.findByTestId('anexo-chip');
    await user.click(screen.getByRole('button', { name: /enviar/i }));

    expect(screen.queryByTestId('anexo-chip')).not.toBeInTheDocument();
  });

  it('recusa arquivo acima do limite de tamanho, nomeando qual', async () => {
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('gigante.pdf', 'application/pdf', 11 * 1024 * 1024)]);

    expect(await screen.findByText(/"gigante.pdf" é maior que 10 MB/i)).toBeInTheDocument();
    expect(extractFileMock).not.toHaveBeenCalled();
  });

  it('uma imagem no lote dispara o consentimento para o lote inteiro', async () => {
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('laudo.pdf'), arquivo('rx.png', 'image/png')]);

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(extractFileMock).not.toHaveBeenCalled();
  });

  it('com consentimento dado, imagem sobe direto', async () => {
    aceitarConsentimentoDeImagem();
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} />);

    await user.upload(input(), [arquivo('rx.png', 'image/png')]);

    expect(await screen.findByTestId('anexo-chip')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('modo Exames', () => {
  it('aparece entre os modos selecionáveis', () => {
    render(<InputBar onSend={vi.fn()} onModeChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /exames/i })).toBeInTheDocument();
  });

  it('pode ser escolhido pelo médico', async () => {
    const onModeChange = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} onModeChange={onModeChange} />);

    await user.click(screen.getByRole('button', { name: /exames/i }));

    expect(onModeChange).toHaveBeenCalledWith('EXAM_REVIEW');
  });
});
