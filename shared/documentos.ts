/**
 * Documentos legais aceitos no onboarding.
 *
 * Ficam centralizados porque o backend grava a VERSAO junto do consentimento
 * (ver app/services/consent_service.py): se um documento for revisado e a data
 * aqui nao subir junto, o registro passa a afirmar que o usuario aceitou um
 * texto que ele nunca viu.
 *
 * Hospedados na central de ajuda da Active (controladora, CNPJ 23.903.127/0001-16).
 */

export const DOCUMENTOS = {
  privacidade: {
    label: 'Política de Privacidade',
    url: 'https://docs.paciente360.com.br/pt-BR/articles/9425687-politica-de-privacidade',
  },
  termos: {
    label: 'Termos de Uso',
    url: 'https://docs.paciente360.com.br/pt-BR/articles/9425689-termo-de-uso',
  },
  cookies: {
    label: 'Política de Cookies',
    url: 'https://docs.paciente360.com.br/pt-BR/articles/9425691-politica-de-cookies',
  },
} as const;

/**
 * Data da ultima revisao dos documentos, no formato que o backend registra.
 *
 * Precisa bater com `VERSAO_DOCUMENTOS` em app/services/consent_service.py.
 */
export const VERSAO_DOCUMENTOS = '2024-08-05';
