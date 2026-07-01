import { expect, type Page } from '@playwright/test';

export const CALCULATOR_PATH = '/calculadoras/risco-cv-sbc2025';

export async function openCalculator(page: Page): Promise<void> {
  await page.goto(CALCULATOR_PATH);
  const modalBtn = page.getByRole('button', { name: /Entendido/i });
  await modalBtn.waitFor({ state: 'visible', timeout: 15_000 });
  await modalBtn.click();
}

function field(page: Page, key: string) {
  return page.locator(`[data-field="${key}"]`);
}

export async function setBool(page: Page, key: string, value: boolean): Promise<void> {
  await field(page, key).getByRole('button', { name: value ? 'Sim' : 'Não', exact: true }).click();
}

export async function setNumber(page: Page, key: string, value: number): Promise<void> {
  await field(page, key).locator('input[type=number]').fill(String(value));
}

export async function setSelect(page: Page, key: string, value: string): Promise<void> {
  await field(page, key).locator('select').selectOption(value);
}

export async function checkMultiOption(page: Page, key: string, optionLabelSubstring: string): Promise<void> {
  await field(page, key).getByText(optionLabelSubstring).click();
}

export async function clickNext(page: Page): Promise<void> {
  await page.getByRole('button', { name: /^Próximo/ }).click();
}

export async function clickBack(page: Page): Promise<void> {
  await page.getByRole('button', { name: /Voltar/ }).click();
}

export async function clickCalcular(page: Page): Promise<void> {
  await page.getByRole('button', { name: /Calcular risco cardiovascular/ }).click();
}

export async function clickComplementarMaisDados(page: Page): Promise<void> {
  await page.getByRole('button', { name: /Complementar mais dados/ }).click();
}

const CATEGORIA_LABEL: Record<string, string> = {
  BAIXO: 'Risco Baixo',
  INTERMEDIARIO: 'Risco Intermediário',
  ALTO: 'Risco Alto',
  MUITO_ALTO: 'Risco Muito Alto',
  EXTREMO: 'Risco Extremo',
};

/** Espera o ResultPanel aparecer e confere categoria + passo determinante. */
export async function expectResult(
  page: Page,
  categoria: keyof typeof CATEGORIA_LABEL,
  passo: number,
  timeout = 15_000
): Promise<void> {
  const panel = page.locator('#result-panel');
  await expect(panel).toBeVisible({ timeout });
  await expect(panel.getByText(CATEGORIA_LABEL[categoria], { exact: true })).toBeVisible();
  await expect(panel.getByText(`Passo ${passo}`, { exact: true })).toBeVisible();
}

/** Confere que o early-exit disparou no passo esperado (banner + resultado), sem avançar o wizard. */
export async function expectEarlyExit(
  page: Page,
  categoria: keyof typeof CATEGORIA_LABEL,
  passo: number
): Promise<void> {
  await expect(page.getByText(`Risco já determinado no Passo ${passo}`)).toBeVisible({ timeout: 15_000 });
  await expectResult(page, categoria, passo);
}

/** Confere que o wizard avançou normalmente para o próximo passo (sem early-exit). */
export async function expectStepperActive(page: Page, stepTitle: string): Promise<void> {
  await expect(page.getByText(stepTitle, { exact: true }).first()).toBeVisible();
}
