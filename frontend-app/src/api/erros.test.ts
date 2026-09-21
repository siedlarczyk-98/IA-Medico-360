/**
 * Cada falha diz ao médico o que aconteceu — e portanto o que fazer.
 *
 * Antes: cota semanal esgotada, sessão expirada e queda de rede mostravam a
 * mesma frase, "Erro ao conectar com o servidor". O médico beta que batia no
 * limite concluía que o produto tinha caído.
 */
import { ErroDeApi, MENSAGEM_SEM_CONEXAO, erroDeResposta, mensagemDeErro } from './erros';

const LIMITE_SEMANAL =
  'Limite semanal de uso atingido. Seu limite será reiniciado em 7 dias a partir da sua primeira interação.';

describe('erroDeResposta', () => {
  it('limite semanal (429 com detail) mostra o texto do backend, inteiro', () => {
    const erro = erroDeResposta(429, JSON.stringify({ detail: LIMITE_SEMANAL }));

    expect(erro.status).toBe(429);
    expect(erro.message).toBe(LIMITE_SEMANAL);
  });

  it('rate limit do slowapi (429 sem detail, em inglês) vira frase em português', () => {
    const erro = erroDeResposta(429, JSON.stringify({ error: 'Rate limit exceeded: 30 per 1 minute' }));

    expect(erro.message).toMatch(/muitas perguntas/i);
    expect(erro.message).not.toMatch(/rate limit/i);
  });

  it('401 diz que a sessão expirou, não que o servidor caiu', () => {
    const erro = erroDeResposta(401, JSON.stringify({ detail: 'Token inválido ou expirado' }));

    expect(erro.message).toMatch(/sessão expirou/i);
  });

  it('5xx nunca repassa o corpo — pode ser stack trace ou HTML de proxy', () => {
    const erro = erroDeResposta(502, '<html><body>Bad Gateway nginx</body></html>');

    expect(erro.message).not.toMatch(/nginx|html/i);
    expect(erro.message).toMatch(/servidor/i);
  });

  it('erro de validação (detail em lista) não vira frase para o médico', () => {
    const erro = erroDeResposta(422, JSON.stringify({ detail: [{ loc: ['body', 'prompt'], msg: 'field required' }] }));

    expect(erro.message).not.toMatch(/field required|loc/);
  });

  it('outros 4xx com detail legível mostram o detail', () => {
    const erro = erroDeResposta(403, JSON.stringify({ detail: 'Conta desativada.' }));

    expect(erro.message).toBe('Conta desativada.');
  });
});

describe('mensagemDeErro', () => {
  it('erro de API fala por si', () => {
    expect(mensagemDeErro(new ErroDeApi(429, LIMITE_SEMANAL))).toBe(LIMITE_SEMANAL);
  });

  it('falha de rede (o fetch nem teve resposta) continua sendo "sem conexão"', () => {
    expect(mensagemDeErro(new TypeError('Failed to fetch'))).toBe(MENSAGEM_SEM_CONEXAO);
  });
});
