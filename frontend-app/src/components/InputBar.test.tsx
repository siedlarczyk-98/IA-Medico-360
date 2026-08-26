/**
 * Item 1: Enter passa a enviar; Shift+Enter quebra linha.
 *
 * O mobile fica de fora de propósito — o Enter do teclado virtual é usado para
 * parágrafo, e enviar ali partiria um caso clínico longo a cada nova linha.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InputBar } from './InputBar';
import { ClarificationPrompt } from './ClarificationPrompt';

/** useIsMobile lê window.innerWidth (breakpoint 768). */
function definirLargura(px: number) {
  Object.defineProperty(window, 'innerWidth', { value: px, writable: true, configurable: true });
}

beforeEach(() => {
  definirLargura(1280); // desktop por padrão
});

describe('InputBar — envio por teclado no desktop', () => {
  it('Enter envia a mensagem', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);

    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), 'dor torácica{Enter}');

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend.mock.calls[0][0]).toBe('dor torácica');
  });

  it('Shift+Enter quebra linha e NÃO envia', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);
    const campo = screen.getByPlaceholderText(/digite sua pergunta/i) as HTMLTextAreaElement;

    await user.type(campo, 'linha um{Shift>}{Enter}{/Shift}linha dois');

    expect(onSend).not.toHaveBeenCalled();
    expect(campo.value).toBe('linha um\nlinha dois');
  });

  it('Ctrl+Enter continua enviando (atalho antigo preservado)', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);

    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), 'caso{Control>}{Enter}{/Control}');

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('Enter em campo vazio não envia nada', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);

    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), '{Enter}');

    expect(onSend).not.toHaveBeenCalled();
  });

  it('mostra a dica de atalho', () => {
    render(<InputBar onSend={vi.fn()} />);
    expect(screen.getByText(/⏎ enviar/)).toBeInTheDocument();
  });
});

describe('InputBar — mobile', () => {
  beforeEach(() => {
    definirLargura(390);
  });

  it('Enter NÃO envia; quebra linha', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);
    const campo = screen.getByPlaceholderText(/digite sua pergunta/i) as HTMLTextAreaElement;

    await user.type(campo, 'primeira{Enter}segunda');

    expect(onSend).not.toHaveBeenCalled();
    expect(campo.value).toBe('primeira\nsegunda');
  });

  it('não mostra a dica de atalho', () => {
    render(<InputBar onSend={vi.fn()} />);
    expect(screen.queryByText(/⏎ enviar/)).not.toBeInTheDocument();
  });

  it('o botão Enviar continua funcionando', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} />);

    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), 'caso');
    await user.click(screen.getByRole('button', { name: /enviar/i }));

    expect(onSend).toHaveBeenCalledTimes(1);
  });
});

describe('ClarificationPrompt — mesma regra do InputBar', () => {
  it('Enter envia a resposta', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ClarificationPrompt onSend={onSend} />);

    await user.type(screen.getByPlaceholderText(/paciente masculino/i), '62 anos{Enter}');

    expect(onSend).toHaveBeenCalledWith('62 anos');
  });

  it('Shift+Enter quebra linha e NÃO envia', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ClarificationPrompt onSend={onSend} />);
    const campo = screen.getByPlaceholderText(/paciente masculino/i) as HTMLTextAreaElement;

    await user.type(campo, 'HAS{Shift>}{Enter}{/Shift}DM2');

    expect(onSend).not.toHaveBeenCalled();
    expect(campo.value).toBe('HAS\nDM2');
  });

  it('no mobile Enter não envia', async () => {
    definirLargura(390);
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ClarificationPrompt onSend={onSend} />);

    await user.type(screen.getByPlaceholderText(/paciente masculino/i), '62 anos{Enter}');

    expect(onSend).not.toHaveBeenCalled();
  });
});
