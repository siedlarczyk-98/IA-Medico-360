import { expect, type Page } from '@playwright/test';

export const CALCULATOR_PATH = '/calculadoras/risco-cv-sbc2025';

/**
 * Helpers do wizard "Risco CV — SBC 2025"
 * (`src/calculators/riscoCv/RiskCalculator.tsx`).
 *
 * A UI é composta pelos primitivos de `src/calculators/riscoCv/ui.tsx`, que não
 * expõem `data-*` de teste: `CheckItem` é um <label> envolvendo o checkbox (o
 * nome acessível vira rótulo + descrição concatenados, então casamos por
 * trecho), `ToggleGroup` é um par de <button>, e `InputField` é um <input> com
 * `id` próprio. Os seletores abaixo se apoiam nisso.
 */

/** Título do CardHeader de cada passo — é o que identifica onde o wizard está. */
export const TITULO_DO_PASSO = {
  triagem: 'Triagem de risco muito alto',
  diabetes: 'Diabetes mellitus',
  altoRisco: 'Condições de alto risco',
  prevent: 'Escore PREVENT',
  agravantes: 'Fatores agravantes (reclassificação)',
} as const;

const ROTULO_DA_CATEGORIA = {
  BAIXO: 'Risco Baixo',
  INTERMEDIARIO: 'Risco Intermediário',
  ALTO: 'Risco Alto',
  MUITO_ALTO: 'Risco Muito Alto',
  EXTREMO: 'Risco Extremo',
} as const;

export async function abrirCalculadora(page: Page): Promise<void> {
  await page.goto(CALCULATOR_PATH);
  await esperarPasso(page, 'triagem');
}

/** Confere em que passo o wizard está. O StepIndicator não serve: ele desenha
 *  os cinco rótulos em qualquer passo, marcando o atual só por estilo. */
export async function esperarPasso(page: Page, passo: keyof typeof TITULO_DO_PASSO): Promise<void> {
  await expect(page.getByText(TITULO_DO_PASSO[passo], { exact: true })).toBeVisible({ timeout: 15_000 });
}

/** Marca um CheckItem (ou um checkbox solto, como os do passo de agravantes). */
export async function marcar(page: Page, rotulo: string): Promise<void> {
  await page.getByRole('checkbox', { name: rotulo }).check();
}

/** Clica uma opção de ToggleGroup (Sim/Não, Masculino/Feminino, mg/dL…). */
export async function escolher(page: Page, opcao: string): Promise<void> {
  await page.getByRole('button', { name: opcao, exact: true }).click();
}

/** Preenche um InputField pelo `id` que o passo lhe deu. */
export async function preencher(page: Page, id: string, valor: number | string): Promise<void> {
  await page.locator(`#${id}`).fill(String(valor));
}

/**
 * Clica o botão primário do passo. O rótulo não é fixo: cada passo troca o texto
 * conforme a decisão já tomada ("Próximo" quando segue o fluxo, "Ver Resultado
 * (Alto)" quando o passo fecha o diagnóstico), e é justamente esse rótulo que
 * revela se houve saída antecipada — por isso ele é sempre explícito nos testes.
 */
export async function avancar(page: Page, rotulo: string | RegExp = /^Próximo/): Promise<void> {
  await page.getByRole('button', { name: rotulo }).click();
}

export async function voltar(page: Page): Promise<void> {
  await page.getByRole('button', { name: /Voltar/ }).click();
}

/** Espera o dashboard final e confere a categoria de risco. */
export async function esperarResultado(page: Page, categoria: keyof typeof ROTULO_DA_CATEGORIA): Promise<void> {
  await expect(page.getByText('Categoria de Risco', { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(ROTULO_DA_CATEGORIA[categoria], { exact: true })).toBeVisible();
}

/** Atravessa Triagem → Diabetes → Alto Risco sem nada marcado, parando no PREVENT. */
export async function irAtePrevent(page: Page): Promise<void> {
  await abrirCalculadora(page);
  await marcar(page, 'Nenhuma das condições acima');
  await avancar(page);
  await esperarPasso(page, 'diabetes');
  await escolher(page, 'Não');
  await avancar(page);
  await esperarPasso(page, 'altoRisco');
  await avancar(page);
  await esperarPasso(page, 'prevent');
}

/** Preenche o bloco clínico do PREVENT e dispara o cálculo (chama o backend). */
export async function calcularPrevent(
  page: Page,
  dados: {
    sexo: 'Masculino' | 'Feminino';
    idade: number;
    ct: number;
    hdl: number;
    sbp: number;
    bmi: number;
    egfr: number;
    fumante?: boolean;
    antiHipertensivo?: boolean;
    estatina?: boolean;
  }
): Promise<void> {
  await escolher(page, dados.sexo);
  await preencher(page, 'prevent-idade', dados.idade);
  await preencher(page, 'prevent-ct', dados.ct);
  await preencher(page, 'prevent-hdl', dados.hdl);
  await preencher(page, 'prevent-sbp', dados.sbp);
  await preencher(page, 'prevent-bmi', dados.bmi);
  await preencher(page, 'prevent-egfr', dados.egfr);
  if (dados.fumante) await marcar(page, 'Tabagismo atual');
  if (dados.antiHipertensivo) await marcar(page, 'Uso de anti-hipertensivo');
  if (dados.estatina) await marcar(page, 'Uso de estatina');
  await avancar(page, 'Calcular PREVENT');
}
