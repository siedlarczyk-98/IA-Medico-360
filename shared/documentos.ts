/**
 * Documentos legais aceitos no onboarding.
 *
 * Ficam centralizados porque o backend grava a VERSAO junto do consentimento
 * (ver app/services/consent_service.py): se um documento for revisado e a data
 * aqui nao subir junto, o registro passa a afirmar que o usuario aceitou um
 * texto que ele nunca viu.
 *
 * Hospedados na central de ajuda da Active (controladora, CNPJ 23.903.127/0001-16).
 *
 * A DATA DE CADA DOCUMENTO FICA AQUI, e nao uma data unica para os tres.
 * Eles sao revisados em momentos diferentes — a de cookies ja estava 10 dias
 * atras das outras duas, e a constante unica escondia isso: o registro de
 * consentimento afirmava uma versao de cookies que nunca existiu. Com as datas
 * a vista, atualizar uma e esquecer a outra vira uma linha visivel no diff.
 *
 * ATENCAO: os textos publicados hoje sao do PACIENTE 360, nao do Medico 360, e
 * a Politica de Privacidade afirma que nao ha compartilhamento com terceiros
 * enquanto a plataforma envia texto clinico para cinco provedores de LLM.
 * Isso esta registrado em docs/pendencias.md e depende de revisao juridica —
 * nao e coisa que se conserte mexendo nestas constantes.
 */

export const DOCUMENTOS = {
  privacidade: {
    label: 'Política de Privacidade',
    url: 'https://docs.paciente360.com.br/pt-BR/articles/9425687-politica-de-privacidade',
    revisao: '2024-08-05',
  },
  termos: {
    label: 'Termos de Uso',
    url: 'https://docs.paciente360.com.br/pt-BR/articles/9425689-termo-de-uso',
    revisao: '2024-08-05',
  },
  cookies: {
    label: 'Política de Cookies',
    url: 'https://docs.paciente360.com.br/pt-BR/articles/9425691-politica-de-cookies',
    // Revisada 10 dias antes das outras duas. Conferido no documento publicado
    // em 2026-09-22: "Última atualização: 26 de julho de 2024".
    revisao: '2024-07-26',
  },
} as const;

/**
 * Versao do CONJUNTO, para o registro de consentimento: a revisao mais recente
 * entre os tres documentos.
 *
 * O aceite e um so e cobre os tres, entao a versao gravada precisa ser uma so.
 * A mais recente e a escolha correta: ela avanca sempre que QUALQUER documento
 * e revisado, e e isso que faz `versao_atual` acusar quem aceitou antes da
 * revisao. Pegar a mais antiga deixaria uma revisao passar em silencio.
 *
 * Precisa bater com `VERSAO_DOCUMENTOS` em app/services/consent_service.py.
 * Ha teste dos dois lados.
 */
export const VERSAO_DOCUMENTOS = Object.values(DOCUMENTOS)
  .map((d) => d.revisao)
  .reduce((mais_recente, revisao) => (revisao > mais_recente ? revisao : mais_recente));
