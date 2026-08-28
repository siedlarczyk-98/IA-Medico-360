import { test, expect } from '@playwright/test';
import { loginAsTestUser } from './helpers/auth';
import {
  abrirCalculadora,
  esperarPasso,
  esperarResultado,
  marcar,
  escolher,
  preencher,
  avancar,
  voltar,
  irAtePrevent,
  calcularPrevent,
} from './helpers/wizard';

/**
 * Cobre o wizard "Risco CV — SBC 2025" (`src/calculators/riscoCv/`), que é 100%
 * client-side: a classificação sai do próprio componente, e o backend só entra
 * no passo do PREVENT (`POST /prevent/calculate`).
 *
 * Não existe "banner de early-exit" nesta UI: a saída antecipada se manifesta no
 * rótulo do botão primário, que troca de "Próximo" para "Ver Resultado (…)"
 * assim que o passo fecha o diagnóstico. Por isso cada teste diz explicitamente
 * qual rótulo espera clicar — é ele que prova em que passo o fluxo terminou.
 */

test.beforeEach(async ({ page }) => {
  await loginAsTestUser(page);
});

test.describe('Passo 1 — Triagem de risco muito alto', () => {
  test('DCVA manifesta + 2 eventos maiores -> EXTREMO', async ({ page }) => {
    await abrirCalculadora(page);
    await marcar(page, 'DCVA manifesta');
    await marcar(page, 'Histórico de infarto do miocárdio');
    await marcar(page, 'Histórico de AVC isquêmico');
    await avancar(page, 'Ver Resultado (Extremo)');
    await esperarResultado(page, 'EXTREMO');
  });

  test('DCVA manifesta + 1 evento maior + 2 condições de alto risco -> EXTREMO', async ({ page }) => {
    await abrirCalculadora(page);
    await marcar(page, 'DCVA manifesta');
    await marcar(page, 'Histórico de infarto do miocárdio');
    await marcar(page, 'Idade ≥ 65 anos');
    await marcar(page, 'Tabagismo atual');
    await avancar(page, 'Ver Resultado (Extremo)');
    await esperarResultado(page, 'EXTREMO');
  });

  test('DCVA manifesta isolada -> MUITO ALTO', async ({ page }) => {
    await abrirCalculadora(page);
    await marcar(page, 'DCVA manifesta');
    await avancar(page, 'Ver Resultado (Muito Alto)');
    await esperarResultado(page, 'MUITO_ALTO');
  });

  test('CAC > 300 UA -> MUITO ALTO', async ({ page }) => {
    await abrirCalculadora(page);
    await marcar(page, 'CAC > 300 UA');
    await avancar(page, 'Ver Resultado (Muito Alto)');
    await esperarResultado(page, 'MUITO_ALTO');
  });

  test('sem nenhuma marcação o botão fica desabilitado', async ({ page }) => {
    await abrirCalculadora(page);
    await expect(page.getByRole('button', { name: /^Próximo/ })).toBeDisabled();
  });
});

test.describe('Passo 2 — Diabetes mellitus', () => {
  /**
   * Com diabetes = Sim o passo exige idade e sexo para liberar o botão, mesmo
   * quando EMAR/EAR já determinam o risco sozinhos — o limiar etário é um dos
   * caminhos de classificação. Os testes de limiar sobrescrevem estes valores.
   */
  async function irAteDiabetes(page: import('@playwright/test').Page) {
    await abrirCalculadora(page);
    await marcar(page, 'Nenhuma das condições acima');
    await avancar(page);
    await esperarPasso(page, 'diabetes');
    await escolher(page, 'Sim');
    await preencher(page, 'dm-age', 45);
    await escolher(page, 'Feminino');
  }

  test('1 EMAR -> MUITO ALTO', async ({ page }) => {
    await irAteDiabetes(page);
    await marcar(page, 'Estenose maior do que 50% em qualquer território vascular');
    await avancar(page, 'Ver Resultado (Muito Alto)');
    await esperarResultado(page, 'MUITO_ALTO');
  });

  test('3 EAR -> MUITO ALTO', async ({ page }) => {
    await irAteDiabetes(page);
    await marcar(page, 'DM2 há mais de 10 anos');
    await marcar(page, 'História familiar de doença arterial coronária prematura');
    await marcar(page, 'Síndrome metabólica definida pelo IDF');
    await avancar(page, 'Ver Resultado (Muito Alto)');
    await esperarResultado(page, 'MUITO_ALTO');
  });

  test('1 EAR -> ALTO', async ({ page }) => {
    await irAteDiabetes(page);
    await marcar(page, 'DM2 há mais de 10 anos');
    await avancar(page, 'Ver Resultado (Alto)');
    await esperarResultado(page, 'ALTO');
  });

  test('sem EAR/EMAR, abaixo do limiar etário (F < 56) -> INTERMEDIÁRIO', async ({ page }) => {
    await irAteDiabetes(page);
    await preencher(page, 'dm-age', 30);
    await escolher(page, 'Feminino');
    await avancar(page, 'Ver Resultado (Intermediário)');
    await esperarResultado(page, 'INTERMEDIARIO');
  });

  test('sem EAR/EMAR, acima do limiar etário (M ≥ 50) -> ALTO', async ({ page }) => {
    await irAteDiabetes(page);
    await preencher(page, 'dm-age', 55);
    await escolher(page, 'Masculino');
    await avancar(page, 'Ver Resultado (Alto)');
    await esperarResultado(page, 'ALTO');
  });
});

test.describe('Passo 3 — Condições de alto risco', () => {
  async function irAteAltoRisco(page: import('@playwright/test').Page) {
    await abrirCalculadora(page);
    await marcar(page, 'Nenhuma das condições acima');
    await avancar(page);
    await esperarPasso(page, 'diabetes');
    await escolher(page, 'Não');
    await avancar(page);
    await esperarPasso(page, 'altoRisco');
  }

  test('LDL-c ≥ 190 -> ALTO', async ({ page }) => {
    await irAteAltoRisco(page);
    await marcar(page, 'LDL-c ≥ 190 mg/dL');
    await avancar(page, 'Ver Resultado (Alto)');
    await esperarResultado(page, 'ALTO');
  });

  test('aterosclerose subclínica -> ALTO', async ({ page }) => {
    await irAteAltoRisco(page);
    await marcar(page, 'Aterosclerose subclínica');
    await avancar(page, 'Ver Resultado (Alto)');
    await esperarResultado(page, 'ALTO');
  });

  test('nada marcado -> segue para o PREVENT', async ({ page }) => {
    await irAteAltoRisco(page);
    await avancar(page);
    await esperarPasso(page, 'prevent');
  });
});

test.describe('Passo 4 — PREVENT', () => {
  const JOVEM_SAUDAVEL = { sexo: 'Feminino', idade: 35, ct: 180, hdl: 60, sbp: 110, bmi: 22, egfr: 100 } as const;

  test('risco < 5% exige LDL-c e fecha BAIXO após os agravantes', async ({ page }) => {
    await irAtePrevent(page);
    await calcularPrevent(page, JOVEM_SAUDAVEL);
    // 35 anos, perfil normal -> ASCVD 0,22%: abaixo de 5%, o passo pede o LDL-c.
    await expect(page.locator('#prevent-score')).toHaveText('0.22%', { timeout: 15_000 });
    await expect(page.getByRole('button', { name: /Informe o LDL-c/ })).toBeDisabled();
    await preencher(page, 'prevent-ldl', 100);
    await avancar(page, 'Avaliar Agravantes');
    await esperarPasso(page, 'agravantes');
    await avancar(page, 'Ver Resultado Final');
    await esperarResultado(page, 'BAIXO');
  });

  test('mesmo perfil com 1 agravante -> reclassifica para INTERMEDIÁRIO', async ({ page }) => {
    await irAtePrevent(page);
    await calcularPrevent(page, JOVEM_SAUDAVEL);
    await expect(page.locator('#prevent-score')).toHaveText('0.22%', { timeout: 15_000 });
    await preencher(page, 'prevent-ldl', 100);
    await avancar(page, 'Avaliar Agravantes');
    await esperarPasso(page, 'agravantes');
    await marcar(page, 'Síndrome metabólica');
    await avancar(page, 'Ver Resultado Final');
    await esperarResultado(page, 'INTERMEDIARIO');
  });

  test('risco >= 20% fecha ALTO sem passar pelos agravantes', async ({ page }) => {
    await irAtePrevent(page);
    await calcularPrevent(page, {
      sexo: 'Masculino', idade: 70, ct: 260, hdl: 32, sbp: 175, bmi: 31, egfr: 48,
      fumante: true, antiHipertensivo: true,
    });
    await expect(page.locator('#prevent-score')).toHaveText('26.24%', { timeout: 15_000 });
    // 70 anos: o risco em 10 anos vale, o de 30 anos não — e a tela precisa dizer por quê.
    await expect(page.getByRole('row', { name: /Aterosclerótica/ })).toContainText('—');
    await expect(page.getByText(/horizonte de 30 anos é validado apenas dos 30 aos 59 anos/)).toBeVisible();
    await avancar(page, 'Ver Resultado (Alto)');
    await esperarResultado(page, 'ALTO');
  });

  test('IMC >= 40 não invalida o ASCVD — só os desfechos de insuficiência cardíaca', async ({ page }) => {
    // Regressão: o backend anulava os seis desfechos quando o IMC saía da faixa,
    // e o wizard tratava isso como "PREVENT não aplicável", rebaixando um obeso
    // grave para a trilha de baixo risco. A AHA invalida desfecho a desfecho.
    await irAtePrevent(page);
    await calcularPrevent(page, {
      sexo: 'Masculino', idade: 55, ct: 220, hdl: 40, sbp: 145, bmi: 42, egfr: 85,
      fumante: true, antiHipertensivo: true,
    });
    await expect(page.locator('#prevent-score')).toHaveText('8.45%', { timeout: 15_000 });
    await expect(page.getByText(/não foi calculado para este paciente/)).toHaveCount(0);
    // A tabela de desfechos vem parcial: sem IC, com as duas colunas de ASCVD.
    await expect(page.getByRole('row', { name: /Insuficiência cardíaca/ })).toContainText('—');
    // E o motivo da lacuna fica explícito, em vez de a célula parecer defeito.
    await expect(page.getByText(/Só as equações de insuficiência cardíaca usam IMC/)).toBeVisible();
    await avancar(page, 'Avaliar Agravantes');
    await esperarPasso(page, 'agravantes');
  });

  test('alternar para mmol/L converte os lipídios exibidos', async ({ page }) => {
    await irAtePrevent(page);
    await calcularPrevent(page, JOVEM_SAUDAVEL);
    await expect(page.locator('#prevent-score')).toHaveText('0.22%', { timeout: 15_000 });
    await escolher(page, 'mmol/L');
    // 180 mg/dL x 0,02586 = 4,65 mmol/L; 60 mg/dL = 1,55 mmol/L.
    await expect(page.locator('#prevent-ct')).toHaveValue('4.65');
    await expect(page.locator('#prevent-hdl')).toHaveValue('1.55');
    await expect(page.getByText('Colesterol total (mmol/L)')).toBeVisible();
  });
});

test.describe('Navegação', () => {
  test('"Voltar" não existe no primeiro passo e retrocede a partir do segundo', async ({ page }) => {
    await abrirCalculadora(page);
    await expect(page.getByRole('button', { name: /Voltar/ })).toHaveCount(0);
    await marcar(page, 'Nenhuma das condições acima');
    await avancar(page);
    await esperarPasso(page, 'diabetes');
    await voltar(page);
    await esperarPasso(page, 'triagem');
  });
});
