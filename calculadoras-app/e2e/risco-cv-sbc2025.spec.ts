import { test, expect } from '@playwright/test';
import { loginAsTestUser } from './helpers/auth';
import {
  openCalculator,
  setBool,
  setNumber,
  setSelect,
  checkMultiOption,
  clickNext,
  clickBack,
  clickCalcular,
  clickComplementarMaisDados,
  expectResult,
  expectEarlyExit,
  expectStepperActive,
} from './helpers/wizard';

// Cobre o algoritmo de estratificação SBC 2025 (app/calculators/formulas/cardiologia/
// risco_cv_sbc2025.py) através da UI do wizard, verificando que o early-exit interrompe
// no passo certo (ou não interrompe, quando o fluxograma só fecha no final).

test.beforeEach(async ({ page }) => {
  await loginAsTestUser(page);
});

test.describe('Passo 1 — Evento CV prévio (Triagem)', () => {
  test('2 eventos maiores -> EXTREMO, interrompe na Triagem', async ({ page }) => {
    await openCalculator(page);
    await setNumber(page, 'idade', 60);
    await setSelect(page, 'sexo', 'M');
    await setBool(page, 'evento_cv_previo', true);
    await checkMultiOption(page, 'tipos_evento_cv', 'Infarto do miocárdio prévio');
    await checkMultiOption(page, 'tipos_evento_cv', 'AVC isquêmico prévio');
    await clickNext(page);
    await expectEarlyExit(page, 'EXTREMO', 1);
  });

  test('1 evento maior + 2 condições de risco extremo -> EXTREMO', async ({ page }) => {
    await openCalculator(page);
    await setNumber(page, 'idade', 60);
    await setSelect(page, 'sexo', 'M');
    await setBool(page, 'evento_cv_previo', true);
    await checkMultiOption(page, 'tipos_evento_cv', 'Infarto do miocárdio prévio');
    await setBool(page, 'cirurgia_revasc_previa_fora_evento', true);
    await setBool(page, 'ldl_persistente_ge100_max_tto', true);
    await setBool(page, 'evento_agudo_lt2anos', false);
    await clickNext(page);
    await expectEarlyExit(page, 'EXTREMO', 1);
  });

  test('1 evento maior, sem condições extras -> MUITO_ALTO', async ({ page }) => {
    await openCalculator(page);
    await setNumber(page, 'idade', 60);
    await setSelect(page, 'sexo', 'M');
    await setBool(page, 'evento_cv_previo', true);
    await checkMultiOption(page, 'tipos_evento_cv', 'Infarto do miocárdio prévio');
    await setBool(page, 'cirurgia_revasc_previa_fora_evento', false);
    await setBool(page, 'ldl_persistente_ge100_max_tto', false);
    await setBool(page, 'evento_agudo_lt2anos', false);
    await clickNext(page);
    await expectEarlyExit(page, 'MUITO_ALTO', 1);
  });
});

test.describe('Passo 2 — Doença aterosclerótica / Passo 4 — marcadores (Alto Risco)', () => {
  async function passTriagemAndDiabetesSemEventos(page: import('@playwright/test').Page, idade: number, sexo: 'M' | 'F') {
    await openCalculator(page);
    await setNumber(page, 'idade', idade);
    await setSelect(page, 'sexo', sexo);
    await setBool(page, 'evento_cv_previo', false);
    await clickNext(page); // Triagem -> Diabetes
    await expectStepperActive(page, 'Diabetes');
    await setBool(page, 'diabetes', false);
    await clickNext(page); // Diabetes -> Alto Risco
    await expectStepperActive(page, 'Alto Risco');
  }

  test('doença aterosclerótica significativa -> MUITO_ALTO (Passo 2)', async ({ page }) => {
    await passTriagemAndDiabetesSemEventos(page, 55, 'M');
    await setBool(page, 'doenca_aterosclerotica_significativa', true);
    await clickNext(page);
    await expectEarlyExit(page, 'MUITO_ALTO', 2);
  });

  test('CAC > 300 -> MUITO_ALTO (Passo 2)', async ({ page }) => {
    await passTriagemAndDiabetesSemEventos(page, 55, 'M');
    await setBool(page, 'doenca_aterosclerotica_significativa', false);
    await setNumber(page, 'cac_ua', 350);
    await clickNext(page);
    await expectEarlyExit(page, 'MUITO_ALTO', 2);
  });

  test('hipercolesterolemia familiar + CAC 100-300 -> MUITO_ALTO (Passo 4)', async ({ page }) => {
    await passTriagemAndDiabetesSemEventos(page, 55, 'M');
    await setBool(page, 'doenca_aterosclerotica_significativa', false);
    await setNumber(page, 'cac_ua', 150);
    await setBool(page, 'hipercolesterolemia_familiar', true);
    await clickNext(page);
    await expectEarlyExit(page, 'MUITO_ALTO', 4);
  });

  test('LDL >= 190 -> ALTO (Passo 4)', async ({ page }) => {
    await passTriagemAndDiabetesSemEventos(page, 55, 'M');
    await setBool(page, 'doenca_aterosclerotica_significativa', false);
    await setNumber(page, 'ldl_mgdl', 200);
    await clickNext(page);
    await expectEarlyExit(page, 'ALTO', 4);
  });

  test('placa carotídea < 50% -> ALTO (Passo 4)', async ({ page }) => {
    await passTriagemAndDiabetesSemEventos(page, 55, 'M');
    await setBool(page, 'doenca_aterosclerotica_significativa', false);
    await setBool(page, 'placa_carotidea_lt50', true);
    await clickNext(page);
    await expectEarlyExit(page, 'ALTO', 4);
  });
});

test.describe('Passo 3 — Diabetes mellitus', () => {
  async function passTriagemSemEvento(page: import('@playwright/test').Page, idade: number, sexo: 'M' | 'F') {
    await openCalculator(page);
    await setNumber(page, 'idade', idade);
    await setSelect(page, 'sexo', sexo);
    await setBool(page, 'evento_cv_previo', false);
    await clickNext(page);
    await expectStepperActive(page, 'Diabetes');
  }

  test('3 EAR -> EMAR -> MUITO_ALTO', async ({ page }) => {
    await passTriagemSemEvento(page, 45, 'F');
    await setBool(page, 'diabetes', true);
    await setNumber(page, 'duracao_dm_anos', 15); // EAR: duração > 10 anos
    await setBool(page, 'historia_familiar_dac_prematura', true); // EAR
    await setBool(page, 'sindrome_metabolica', true); // EAR
    await clickNext(page);
    await expectEarlyExit(page, 'MUITO_ALTO', 3);
  });

  test('1 EAR -> ALTO', async ({ page }) => {
    await passTriagemSemEvento(page, 45, 'F');
    await setBool(page, 'diabetes', true);
    await setNumber(page, 'duracao_dm_anos', 15); // único EAR
    await clickNext(page);
    await expectEarlyExit(page, 'ALTO', 3);
  });

  test('sem EAR/EMAR, idade abaixo do limiar -> INTERMEDIARIO', async ({ page }) => {
    await passTriagemSemEvento(page, 30, 'F'); // F < 56 anos
    await setBool(page, 'diabetes', true);
    await clickNext(page);
    await expectEarlyExit(page, 'INTERMEDIARIO', 3);
  });

  test('sem EAR/EMAR, idade acima do limiar -> ALTO', async ({ page }) => {
    await passTriagemSemEvento(page, 55, 'M'); // M >= 50 anos
    await setBool(page, 'diabetes', true);
    await clickNext(page);
    await expectEarlyExit(page, 'ALTO', 3);
  });
});

test.describe('Passo 5 — PREVENT + Agravantes (fluxo completo, sem early-exit até o fim)', () => {
  async function chegarNoPrevent(page: import('@playwright/test').Page, idade: number, sexo: 'M' | 'F') {
    await openCalculator(page);
    await setNumber(page, 'idade', idade);
    await setSelect(page, 'sexo', sexo);
    await setBool(page, 'evento_cv_previo', false);
    await clickNext(page);
    await expectStepperActive(page, 'Diabetes');
    await setBool(page, 'diabetes', false);
    await clickNext(page);
    await expectStepperActive(page, 'Alto Risco');
    await setBool(page, 'doenca_aterosclerotica_significativa', false);
    await setNumber(page, 'ldl_mgdl', 100);
    await clickNext(page);
    await expectStepperActive(page, 'PREVENT');
  }

  test('paciente jovem, sem fatores de risco -> chega até Agravantes e fecha BAIXO', async ({ page }) => {
    await chegarNoPrevent(page, 35, 'F');
    await setNumber(page, 'ct_mgdl', 180);
    await setNumber(page, 'hdl_mgdl', 60);
    await setNumber(page, 'sbp_mmhg', 110);
    await setNumber(page, 'bmi', 22);
    await setNumber(page, 'egfr', 100);
    await setBool(page, 'fumante', false);
    await setBool(page, 'antihtn_use', false);
    await setBool(page, 'statin_use', false);
    await setBool(page, 'hipertensao', false);
    await clickNext(page);
    // PREVENT nunca early-exita sozinho — deve avançar para Agravantes.
    await expectStepperActive(page, 'Agravantes');
    await clickCalcular(page);
    await expectResult(page, 'BAIXO', 5);
  });

  test('mesmo perfil, mas com 1 fator agravante -> INTERMEDIARIO', async ({ page }) => {
    await chegarNoPrevent(page, 35, 'F');
    await setNumber(page, 'ct_mgdl', 180);
    await setNumber(page, 'hdl_mgdl', 60);
    await setNumber(page, 'sbp_mmhg', 110);
    await setNumber(page, 'bmi', 22);
    await setNumber(page, 'egfr', 100);
    await setBool(page, 'fumante', false);
    await setBool(page, 'antihtn_use', false);
    await setBool(page, 'statin_use', false);
    await setBool(page, 'hipertensao', false);
    await clickNext(page);
    await expectStepperActive(page, 'Agravantes');
    await setBool(page, 'historia_familiar_cv_prematura', true);
    await clickCalcular(page);
    await expectResult(page, 'INTERMEDIARIO', 5);
  });
});

test.describe('UX de early-exit', () => {
  test('"Complementar mais dados" limpa o early-exit e permite continuar o wizard', async ({ page }) => {
    await openCalculator(page);
    await setNumber(page, 'idade', 60);
    await setSelect(page, 'sexo', 'M');
    await setBool(page, 'evento_cv_previo', true);
    await checkMultiOption(page, 'tipos_evento_cv', 'Infarto do miocárdio prévio');
    await checkMultiOption(page, 'tipos_evento_cv', 'AVC isquêmico prévio');
    await clickNext(page);
    await expectEarlyExit(page, 'EXTREMO', 1);

    await clickComplementarMaisDados(page);
    await expectStepperActive(page, 'Diabetes');
  });

  test('"Voltar" no primeiro passo não aparece; a partir do 2º passo permite retroceder', async ({ page }) => {
    await openCalculator(page);
    await setNumber(page, 'idade', 55);
    await setSelect(page, 'sexo', 'M');
    await setBool(page, 'evento_cv_previo', false);
    await expect(page.getByRole('button', { name: /Voltar/ })).toHaveCount(0);
    await clickNext(page);
    await expectStepperActive(page, 'Diabetes');
    await clickBack(page);
    await expectStepperActive(page, 'Triagem');
  });
});

test.describe('Validação', () => {
  test('não avança sem idade/sexo preenchidos', async ({ page }) => {
    await openCalculator(page);
    await setBool(page, 'evento_cv_previo', false);
    await clickNext(page);
    // Continua na Triagem — não deve ter avançado nem mostrado resultado.
    await expect(page.locator('#result-panel')).toHaveCount(0);
    await expect(page.locator('[data-field="idade"]').getByText('Campo obrigatório')).toBeVisible();
  });
});
