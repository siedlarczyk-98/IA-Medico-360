/**
 * Formulário que sobrevive à reentrada (`shared/embed/formulario.ts`, item 63).
 *
 * Mora aqui porque as calculadoras, que são as que usam, não têm runner de teste
 * unitário — só o e2e do Playwright. O módulo é compartilhado e não depende de
 * nada deste app.
 *
 * As duas metades importam igual: o que o médico preencheu VOLTA depois da
 * reentrada, e NÃO volta em nenhum outro caso — reabrir a calculadora preenchida
 * traria os dados do paciente anterior.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';

import {
  formularioAberto,
  guardarFormulariosAbertos,
  useFormularioSalvo,
  usePreservarFormulario,
} from '@shared/embed/formulario';

function Formulario({ dono, chave = 'curb65' }: { dono: string | null; chave?: string }) {
  const salvo = useFormularioSalvo<{ idade: string }>(chave, dono);
  const [idade, setIdade] = useState(salvo?.idade ?? '');
  usePreservarFormulario(chave, { idade });
  return <input aria-label="idade" value={idade} onChange={e => setIdade(e.target.value)} />;
}

function preencher(valor: string) {
  fireEvent.change(screen.getByLabelText('idade'), { target: { value: valor } });
}

const campo = () => screen.getByLabelText('idade') as HTMLInputElement;

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.useRealTimers());

it('o que foi preenchido volta depois da reentrada, para o mesmo médico', () => {
  const { unmount } = render(<Formulario dono="medico-1" />);
  preencher('72');

  guardarFormulariosAbertos('medico-1'); // o `sessaoExpirou`, antes de navegar
  unmount(); // a navegação completa derruba a página

  render(<Formulario dono="medico-1" />);
  expect(campo().value).toBe('72');
});

it('reabrir a calculadora SEM reentrada começa vazio: nada de dados do paciente anterior', () => {
  const { unmount } = render(<Formulario dono="medico-1" />);
  preencher('72');
  unmount();

  render(<Formulario dono="medico-1" />);
  expect(campo().value).toBe('');
});

it('o guardado é consumido: volta uma vez, e não na próxima abertura', () => {
  const primeira = render(<Formulario dono="medico-1" />);
  preencher('72');
  guardarFormulariosAbertos('medico-1');
  primeira.unmount();

  const segunda = render(<Formulario dono="medico-1" />);
  expect(campo().value).toBe('72');
  segunda.unmount();

  render(<Formulario dono="medico-1" />);
  expect(campo().value).toBe('');
});

it('NÃO volta para outro médico', () => {
  // Estação compartilhada: quem entra pelo login depois da queda pode ser outro.
  const { unmount } = render(<Formulario dono="medico-1" />);
  preencher('72');
  guardarFormulariosAbertos('medico-1');
  unmount();

  render(<Formulario dono="medico-2" />);
  expect(campo().value).toBe('');
});

it('não volta depois do prazo', () => {
  vi.useFakeTimers();
  const { unmount } = render(<Formulario dono="medico-1" />);
  preencher('72');
  guardarFormulariosAbertos('medico-1');
  unmount();

  act(() => { vi.advanceTimersByTime(31 * 60 * 1000); });

  render(<Formulario dono="medico-1" />);
  expect(campo().value).toBe('');
});

it('sem dono conhecido, nada é guardado', () => {
  const { unmount } = render(<Formulario dono="medico-1" />);
  preencher('72');
  guardarFormulariosAbertos(undefined);
  unmount();

  expect(sessionStorage.length).toBe(0);
});

it('só guarda o que está aberto, cada um na sua chave', () => {
  const aberto = render(<Formulario dono="medico-1" chave="generico:curb65" />);
  preencher('72');
  const fechado = render(<Formulario dono="medico-1" chave="generico:cockcroft" />);
  fechado.unmount();

  guardarFormulariosAbertos('medico-1');
  aberto.unmount();

  expect(Object.keys(sessionStorage)).toEqual(['m360_formulario:generico:curb65']);
});

it('formulário ainda carregando (estado `undefined`) não é guardado', () => {
  // As notícias carregam os temas do servidor ao abrir, e o 401 cai justamente
  // nessas chamadas. Guardar o "nada marcado" daquele instante faria a volta
  // mostrar tudo desmarcado — e um toque em salvar apagaria os temas.
  function Carregando() {
    usePreservarFormulario('temas', undefined);
    return null;
  }
  const { unmount } = render(<Carregando />);

  expect(formularioAberto('temas')).toBe(false);
  guardarFormulariosAbertos('medico-1');
  unmount();

  expect(sessionStorage.length).toBe(0);
});

it('formularioAberto diz se a tela está montada e registrada', () => {
  const { unmount } = render(<Formulario dono="medico-1" chave="temas" />);
  expect(formularioAberto('temas')).toBe(true);
  unmount();
  expect(formularioAberto('temas')).toBe(false);
});
