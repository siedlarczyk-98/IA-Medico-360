/**
 * A tela de espera da entrada — igual nos três apps (chat, calculadoras,
 * notícias).
 *
 * Cada app tinha a sua: o chat e as calculadoras, um spinner com
 * "Confirmando sua identidade…" (duas cópias que já tinham começado a divergir);
 * as notícias, só um "Carregando…" em texto puro, que nem dizia o que estava
 * acontecendo. É a primeira coisa que o médico vê ao abrir qualquer seção do
 * Médico 360 dentro da Waid — tinha de ser uma só.
 *
 * As cores vêm dos tokens do app com a cor da marca de reserva (`var(--mint,
 * #aef6c6)`): as notícias não definem essas variáveis, e sem a reserva o
 * spinner ficaria invisível lá.
 */

import type { FaseIdentidade } from './identidade';

/** O que dizer enquanto o handshake com a Waid acontece. */
export function mensagemDaIdentidade(fase: FaseIdentidade): string {
  return fase === 'trocando' ? 'Confirmando sua identidade…' : 'Autenticando…';
}

export function TelaDeEspera({ mensagem }: { mensagem: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--fill2, #f5f7f6)',
      }}
    >
      <div style={{ textAlign: 'center' }}>
        <div
          aria-hidden="true"
          style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            border: '3px solid var(--mint, #aef6c6)',
            borderTopColor: 'var(--green, #00d17d)',
            animation: 'm360-espera-giro 0.8s linear infinite',
            margin: '0 auto 16px',
          }}
        />
        <p style={{ margin: 0, fontSize: 'var(--texto-apoio, 14px)', color: 'var(--pen2, #6b7a80)' }}>
          {mensagem}
        </p>
        <style>{'@keyframes m360-espera-giro { to { transform: rotate(360deg); } }'}</style>
      </div>
    </div>
  );
}
