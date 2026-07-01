import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import jwt from 'jsonwebtoken';
import type { Page } from '@playwright/test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// O login real é por magic-link/OTP por e-mail, o que não dá para automatizar em CI.
// Para os testes E2E, assinamos um token localmente com o mesmo segredo/algoritmo do
// backend (lido do .env da raiz do monorepo) para um usuário de teste já existente no
// banco — equivalente a "logar" sem passar pelo fluxo de e-mail.
function readRootEnv(key: string): string | undefined {
  const envPath = path.resolve(__dirname, '../../../.env');
  if (!fs.existsSync(envPath)) return undefined;
  const content = fs.readFileSync(envPath, 'utf-8');
  const match = content.match(new RegExp(`^${key}=(.*)$`, 'm'));
  return match?.[1]?.trim();
}

const JWT_SECRET = process.env.E2E_JWT_SECRET ?? readRootEnv('JWT_SECRET_KEY');
const JWT_ALGORITHM = (process.env.E2E_JWT_ALGORITHM ?? readRootEnv('JWT_ALGORITHM') ?? 'HS256') as jwt.Algorithm;

// Usuário de teste já existente no banco de dev (ver users.email = 'dev@medico360.local').
// Sobrescreva via env se necessário em outro ambiente.
const TEST_USER_ID = process.env.E2E_TEST_USER_ID ?? 'c7b85085-dcd7-437c-89ba-e419c16bcff8';
const TEST_USER_ROLE = process.env.E2E_TEST_USER_ROLE ?? 'free_user';

export function mintTestToken(): string {
  if (!JWT_SECRET) {
    throw new Error(
      'JWT_SECRET_KEY não encontrado. Defina E2E_JWT_SECRET ou garanta que o .env na raiz do projeto tenha JWT_SECRET_KEY.'
    );
  }
  return jwt.sign(
    { sub: TEST_USER_ID, role: TEST_USER_ROLE },
    JWT_SECRET,
    { algorithm: JWT_ALGORITHM, expiresIn: '2h' }
  );
}

export async function loginAsTestUser(page: Page): Promise<void> {
  const token = mintTestToken();
  // localStorage só pode ser setado depois de navegar para a origem correta.
  await page.goto('/');
  await page.evaluate((t) => localStorage.setItem('calc360_token', t), token);
}
