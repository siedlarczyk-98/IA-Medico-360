// Email/nome chegam pre-preenchidos na URL (mesmo padrao do EmbedAuthPage
// dos outros apps do repo) — o lead nao preenche esses campos, so as
// perguntas da LP. `emailMissing` marca explicitamente quando o fornecedor
// do embedding nao mandou o email, pra reportar pra ele — sem essa flag,
// "email nulo" fica ambiguo com o tempo (fornecedor falhou vs. LP que nem
// pede email).
export function getLeadFromUrl() {
  const params = new URLSearchParams(window.location.search)
  const email = params.get('email') || undefined
  return {
    email,
    name: params.get('name') || undefined,
    emailMissing: !email,
  }
}
