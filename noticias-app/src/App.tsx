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
import { useCallback, useEffect, useState } from 'react';
import HighlightsMagazine from './components/HighlightsMagazine';
import { TemasPage } from './pages/TemasPage';
import { buscarMeusTemas } from './api/news';
import { OnboardingGate } from '@shared/onboarding/OnboardingGate';
import { useIdentidadeWaid } from '@shared/embed/identidade';
import { LoginOtp } from '@shared/embed/LoginOtp';
import { clearToken, descartarSessaoDesteNavegador, getToken, isTokenExpired, setToken } from './lib/auth';

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const WAID_ORIGIN =
  import.meta.env.VITE_WAID_ORIGIN ?? 'https://www.medico360.app';

type Estado =
  | { fase: 'carregando' }
  | { fase: 'login'; motivo: string }
  | { fase: 'erro'; mensagem: string }
  | { fase: 'temas'; primeiraVez: boolean }
  | { fase: 'feed' };

export default function App() {
  const [estado, setEstado] = useState<Estado>({ fase: 'carregando' });

  /** Com sessão em mãos, decide entre a escolha de temas e o feed. */
  const carregarConteudo = useCallback(async () => {
    try {
      // A tela de escolha só aparece a quem nunca escolheu. Quem decidiu não
      // marcar nada não pode ser reapresentado a ela toda visita — daí o
      // marcador ser "já escolheu", e não "tem temas".
      const temas = await buscarMeusTemas();
      setEstado(temas.ja_escolheu ? { fase: 'feed' } : { fase: 'temas', primeiraVez: true });
    } catch (e) {
      setEstado({ fase: 'erro', mensagem: e instanceof Error ? e.message : 'Erro ao iniciar' });
    }
  }, []);

  // A identidade vem do handshake com a Waid, não mais do `?email=` da URL.
  //
  // O token guardado NÃO é mais apagado na montagem. Apagar era a proteção contra
  // herdar a sessão de outro médico, mas cobrava de quem não tinha nada a ver com
  // o risco: nos aplicativos da Waid a seção abre SEM iframe, o handshake é
  // impossível, e o médico digitava um código por e-mail A CADA ABERTURA. A
  // proteção continua, só que mirada (ver o efeito de `identidade.fase` abaixo):
  // o token só é usado depois que o handshake se resolve, e é descartado quando a
  // plataforma deveria ter dito quem é o médico e não disse.
  const identidade = useIdentidadeWaid({
    apiBase: API_BASE,
    waidOrigin: WAID_ORIGIN,
    aoAutenticar: resposta => {
      setToken(resposta.access_token);
      void carregarConteudo();
    },
  });

  useEffect(() => {
    if (identidade.fase !== 'erro') return;
    const semIframe = identidade.erro?.tipo === 'sem_iframe';

    const pedirLogin = () => setEstado({
      fase: 'login',
      motivo: semIframe
        ? 'No aplicativo, entre pelo seu e-mail. Pelo navegador, o acesso é automático.'
        : 'Não conseguimos confirmar sua identidade com a plataforma.',
    });

    if (!semIframe) {
      // DENTRO do iframe e sem identidade confirmada: a sessão que estava neste
      // navegador pode ser de quem usou a máquina antes. Não se herda.
      descartarSessaoDesteNavegador();
      pedirLogin();
      return;
    }

    // Fora de iframe — o aplicativo da Waid, aparelho pessoal. Se o login por
    // e-mail de antes ainda vale, é ele que entra; só pede código de novo quando
    // a sessão venceu (no máximo uma vez por dia).
    if (!getToken() || isTokenExpired()) {
      clearToken();
      pedirLogin();
      return;
    }
    buscarMeusTemas()
      .then(temas => setEstado(temas.ja_escolheu ? { fase: 'feed' } : { fase: 'temas', primeiraVez: true }))
      .catch(() => {
        // O servidor recusou (sessão revogada por um "Sair" em outro lugar).
        clearToken();
        pedirLogin();
      });
  }, [identidade.fase, identidade.erro]);

  if (estado.fase === 'carregando') {
    return <div style={aviso}>Carregando…</div>;
  }

  if (estado.fase === 'erro') {
    return <div style={{ ...aviso, color: '#a13a12' }}>{estado.mensagem}</div>;
  }

  if (estado.fase === 'login') {
    return (
      <LoginOtp
        apiBase={API_BASE}
        titulo="Notícias"
        aviso={estado.motivo}
        aoAutenticar={token => {
          setToken(token);
          setEstado({ fase: 'carregando' });
          void carregarConteudo();
        }}
      />
    );
  }

  const conteudo = estado.fase === 'temas'
    ? (
      <TemasPage
        primeiraVez={estado.primeiraVez}
        aoConcluir={() => setEstado({ fase: 'feed' })}
        // Sair sem salvar so faz sentido para quem ja tem um feed para voltar.
        aoCancelar={estado.primeiraVez ? undefined : () => setEstado({ fase: 'feed' })}
      />
    )
    : <HighlightsMagazine aoEditarTemas={() => setEstado({ fase: 'temas', primeiraVez: false })} />;

  // O gate vem ANTES da escolha de temas, de proposito: a TemasPage pre-marca
  // os temas a partir da especialidade, e sem ela cai num fallback generico.
  // Completar o perfil primeiro e o que faz aquela tela chegar ja preenchida.
  // Mesma tela dos outros dois apps, importada de `shared/` — o medico preenche
  // uma vez, em qualquer porta de entrada, e serve para todos.
  return (
    <OnboardingGate
      apiBase={API_BASE}
      token={getToken()}
      aoConcluir={t => { setToken(t); window.location.reload(); }}
    >
      {conteudo}
    </OnboardingGate>
  );
}

const aviso: React.CSSProperties = {
  padding: 48,
  textAlign: 'center',
  fontFamily: "var(--m360-font, 'Just Sans', -apple-system, 'Segoe UI', sans-serif)",
  color: '#014751',
};
