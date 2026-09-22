/**
 * A página está dentro de um iframe?
 *
 * Os apps rodam em dois contextos, e a interface deve mudar entre eles:
 *
 * - DENTRO do iframe (área de membros, no navegador): a identidade vem do
 *   handshake com a Waid, a cada abertura. Um botão "Sair" ali não tem sentido —
 *   o médico não escolheu entrar nem consegue "não estar logado": recarregar
 *   autentica de novo. O que o botão faz é ocupar espaço e sugerir um estado que
 *   não existe.
 * - FORA do iframe (aplicativo da Waid, que abre a seção sem iframe): o acesso é
 *   por código de e-mail e a sessão dura até 24 h. Aí "Sair" é necessário — é a
 *   única forma de trocar de conta num aparelho compartilhado.
 *
 * `window.top` de outra origem levanta `SecurityError` ao ser comparado em alguns
 * navegadores; nesse caso, estar em iframe é a conclusão certa.
 */
export function dentroDoIframe(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
}
