/**
 * App de notícias do Médico 360.
 *
 * Pensado para abrir dentro de um <iframe> no LMS. A identidade vem do SSO de
 * embed (`/auth/embed/token`), o mesmo que o app principal usa: o LMS monta a
 * URL com `?email=`, trocamos por um JWT de verdade, e daí em diante toda
 * chamada vai autenticada.
 *
 * O `?email=` NÃO é mais a identidade — é só a semente da troca. A diferença
 * importa: o feed é personalizado, e aceitar um e-mail cru como identidade
 * permitiria a qualquer um ler e alterar os temas de outra pessoa.
 */
import { useEffect, useState } from 'react';
import HighlightsMagazine from './components/HighlightsMagazine';
import { TemasPage } from './pages/TemasPage';
import { autenticarEmbed, buscarMeusTemas } from './api/news';
import { clearToken, isAuthenticated, isTokenExpired, setToken, tokenEhDeOutroEmail } from './lib/auth';

type Estado =
  | { fase: 'carregando' }
  | { fase: 'erro'; mensagem: string }
  | { fase: 'temas'; primeiraVez: boolean }
  | { fase: 'feed' };

export default function App() {
  const [estado, setEstado] = useState<Estado>({ fase: 'carregando' });

  useEffect(() => {
    let cancelado = false;

    async function iniciar() {
      try {
        const email = new URLSearchParams(window.location.search).get('email');

        // Reautentica também quando o e-mail da URL é OUTRO — não só quando
        // falta token ou ele expirou. Sem essa condição, o segundo usuário a
        // abrir o LMS no mesmo navegador herdaria a sessão do primeiro e veria
        // o feed, os temas e os favoritos dele até o token vencer.
        const precisaAutenticar =
          !isAuthenticated() || isTokenExpired() || (!!email && tokenEhDeOutroEmail(email));

        if (precisaAutenticar) {
          if (!email) {
            throw new Error(
              'Sessão não identificada. Abra o módulo de notícias a partir do portal.'
            );
          }
          clearToken();
          const { access_token } = await autenticarEmbed(email);
          setToken(access_token, email);
        }

        // A tela de escolha só aparece a quem nunca escolheu. Quem decidiu não
        // marcar nada não pode ser reapresentado a ela toda visita — daí o
        // marcador ser "já escolheu", e não "tem temas".
        const temas = await buscarMeusTemas();
        if (cancelado) return;
        setEstado(temas.ja_escolheu ? { fase: 'feed' } : { fase: 'temas', primeiraVez: true });
      } catch (e) {
        if (!cancelado) {
          setEstado({ fase: 'erro', mensagem: e instanceof Error ? e.message : 'Erro ao iniciar' });
        }
      }
    }

    iniciar();
    return () => {
      cancelado = true;
    };
  }, []);

  if (estado.fase === 'carregando') {
    return <div style={aviso}>Carregando…</div>;
  }

  if (estado.fase === 'erro') {
    return <div style={{ ...aviso, color: '#a13a12' }}>{estado.mensagem}</div>;
  }

  if (estado.fase === 'temas') {
    return (
      <TemasPage
        primeiraVez={estado.primeiraVez}
        aoConcluir={() => setEstado({ fase: 'feed' })}
      />
    );
  }

  return <HighlightsMagazine aoEditarTemas={() => setEstado({ fase: 'temas', primeiraVez: false })} />;
}

const aviso: React.CSSProperties = {
  padding: 48,
  textAlign: 'center',
  fontFamily: "var(--m360-font, 'Just Sans', -apple-system, 'Segoe UI', sans-serif)",
  color: '#014751',
};
