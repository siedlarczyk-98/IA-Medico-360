/**
 * Login por código de e-mail (OTP), autossuficiente.
 *
 * POR QUE EM `shared/`
 * O `frontend-app` e o `calculadoras-app` já têm esta tela — dois arquivos de
 * 222 linhas com **12 linhas diferentes** entre si (logo, título e destino da
 * navegação). O `noticias-app` NÃO TINHA NENHUMA: no aplicativo da Waid, onde o
 * embed não funciona, o médico via "Sessão não identificada" e ficava sem
 * saída. Escrever uma quarta cópia seria repetir o erro de propósito.
 *
 * POR QUE ISTO VIROU NECESSÁRIO AGORA
 * Enquanto a identidade vinha na URL, o embed era a única porta e ninguém
 * pensava em alternativa. Com o handshake — e sabendo que ele é impossível nos
 * aplicativos da Waid, que abrem a seção sem iframe — o OTP deixou de ser
 * contorno e virou **o caminho de entrada no mobile**. Um app sem ele fica
 * inacessível ali.
 *
 * AUTOSSUFICIENTE POR NECESSIDADE
 * Sem react-router (o `noticias-app` não usa) e sem variáveis de CSS (ele não
 * define nenhuma). Estilos e paleta vêm de `estilos.ts`, o mesmo do onboarding.
 *
 * O `frontend-app` e o `calculadoras-app` deveriam adotar este componente e
 * apagar as próprias cópias — mas as delas FUNCIONAM, e trocar auth que
 * funciona por auth nova sem ganho para o usuário é risco sem retorno. Fica
 * como limpeza para quando alguém precisar mexer naquelas telas.
 */

import { useState } from 'react';

import * as s from '../onboarding/estilos';

interface Props {
  apiBase: string;
  /** Título do cartão — o nome do módulo em que o médico está entrando. */
  titulo: string;
  /** Chamado com o token quando o código é aceito. */
  aoAutenticar: (accessToken: string) => void;
  /** Texto acima do formulário. Útil para explicar por que ele caiu aqui. */
  aviso?: string;
}

async function chamar(apiBase: string, caminho: string, corpo: unknown): Promise<Response> {
  const resp = await fetch(`${apiBase}/api/v1${caminho}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(corpo),
  });
  if (!resp.ok) {
    const detalhe = await resp.json().catch(() => null);
    const msg = typeof detalhe?.detail === 'string' ? detalhe.detail : `Erro ${resp.status}`;
    throw new Error(msg);
  }
  return resp;
}

export function LoginOtp({ apiBase, titulo, aoAutenticar, aviso }: Props) {
  const [etapa, setEtapa] = useState<'email' | 'codigo'>('email');
  const [email, setEmail] = useState('');
  const [codigo, setCodigo] = useState('');
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);

  async function pedirCodigo(e: React.FormEvent) {
    e.preventDefault();
    setErro('');
    setEnviando(true);
    try {
      await chamar(apiBase, '/auth/otp/request', { email: email.trim().toLowerCase() });
      setEtapa('codigo');
    } catch (err) {
      setErro(err instanceof Error ? err.message : 'Não foi possível enviar o código.');
    } finally {
      setEnviando(false);
    }
  }

  async function conferirCodigo(e: React.FormEvent) {
    e.preventDefault();
    setErro('');
    setEnviando(true);
    try {
      const resp = await chamar(apiBase, '/auth/otp/verify', {
        email: email.trim().toLowerCase(),
        code: codigo,
      });
      const { access_token } = await resp.json();
      aoAutenticar(access_token);
    } catch (err) {
      setErro(err instanceof Error ? err.message : 'Código inválido.');
    } finally {
      setEnviando(false);
    }
  }

  const naEtapaEmail = etapa === 'email';
  const podeEnviar = naEtapaEmail
    ? email.includes('@') && email.trim().length > 3
    : codigo.trim().length === 6;

  return (
    <div style={s.fundo}>
      <style>{s.CSS_GLOBAL}</style>

      <form style={s.cartao} onSubmit={naEtapaEmail ? pedirCodigo : conferirCodigo}>
        <h1 style={s.titulo}>{titulo}</h1>
        <p style={s.subtitulo}>
          {naEtapaEmail
            ? (aviso ?? 'Enviamos um código de acesso para o seu e-mail.')
            : 'Digite o código de 6 dígitos que enviamos.'}
        </p>

        {naEtapaEmail ? (
          <div style={{ marginBottom: 18 }}>
            <label style={s.rotulo} htmlFor="otp-email">E-mail</label>
            <input
              id="otp-email"
              className="m360-ob-campo"
              style={s.campo}
              type="email"
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={ev => setEmail(ev.target.value)}
              placeholder="seu@email.com"
            />
          </div>
        ) : (
          <div style={{ marginBottom: 18 }}>
            <label style={s.rotulo} htmlFor="otp-codigo">Código</label>
            <input
              id="otp-codigo"
              className="m360-ob-campo"
              style={{ ...s.campo, letterSpacing: '0.4em', fontSize: 18, textAlign: 'center' }}
              inputMode="numeric"
              autoComplete="one-time-code"
              value={codigo}
              onChange={ev => setCodigo(ev.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
            />
            <p style={{ fontSize: 12.5, color: s.CORES.pen2, margin: '8px 0 0' }}>
              Enviado para <strong style={{ color: s.CORES.ink }}>{email}</strong>.{' '}
              <button
                type="button"
                onClick={() => { setEtapa('email'); setCodigo(''); setErro(''); }}
                style={{
                  background: 'none', border: 'none', padding: 0,
                  color: s.CORES.petrol, font: 'inherit', fontWeight: 600,
                  textDecoration: 'underline', cursor: 'pointer',
                }}
              >
                Trocar
              </button>
            </p>
          </div>
        )}

        {erro && <p role="alert" style={s.erro}>{erro}</p>}

        <button
          type="submit"
          className="m360-ob-botao"
          disabled={!podeEnviar || enviando}
          style={s.botao(podeEnviar && !enviando)}
        >
          {enviando
            ? 'Aguarde…'
            : naEtapaEmail ? 'Receber código' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}
