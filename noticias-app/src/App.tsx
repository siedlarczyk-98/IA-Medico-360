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
import { Route, Routes, useNavigate, useParams } from 'react-router-dom';
import HighlightsMagazine from './components/HighlightsMagazine';
import { TemasPage } from './pages/TemasPage';
import { buscarMeusTemas } from './api/news';
import { OnboardingGate } from '@shared/onboarding/OnboardingGate';
import { montarOrigensWaid, temIframe, useIdentidadeWaid } from '@shared/embed/identidade';
import { useSessaoViva } from '@shared/embed/sessao';
import { LoginOtp } from '@shared/embed/LoginOtp';
import { mensagemDaIdentidade, TelaDeEspera } from '@shared/embed/TelaDeEspera';
import {
  clearToken,
  descartarSessaoDesteNavegador,
  getToken,
  isTokenExpired,
  sessaoExpirou,
  setToken,
} from './lib/auth';

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const WAID_ORIGIN =
  import.meta.env.VITE_WAID_ORIGIN ?? 'https://www.medico360.app';

/**
 * Duas origens, não uma: o embed no navegador responde do portal da Waid; o
 * app nativo responde do domínio público. Ver `montarOrigensWaid`.
 */
const ORIGENS_WAID = montarOrigensWaid(WAID_ORIGIN);

type Estado =
  | { fase: 'carregando' }
  | { fase: 'login'; motivo: string }
  | { fase: 'erro'; mensagem: string }
  | { fase: 'temas'; primeiraVez: boolean }
  | { fase: 'feed' };

/**
 * O médico chegou por um link que pede uma tela específica (`/artigo/153` do
 * digest, `/preferencias` do descadastro)?
 *
 * Lê `window.location` e não o roteador de propósito: isto roda no fluxo de
 * autenticação, que vive FORA das rotas (ver o comentário em `conteudo`).
 * Usar `useLocation` aqui exigiria mover o handshake para dentro do roteador,
 * e aí `/artigo/:id` viraria uma rota alcançável sem sessão.
 */
function temEntradaDireta(): boolean {
  const caminho = window.location.pathname;
  return caminho.startsWith('/artigo/') || caminho === '/preferencias';
}

export default function App() {
  const [estado, setEstado] = useState<Estado>({ fase: 'carregando' });

  // Renova o token antes de vencer; se o app volta do segundo plano com ele já
  // vencido, recarrega para refazer a entrada. Ver `shared/embed/sessao.ts`.
  useSessaoViva({ apiBase: API_BASE, getToken, setToken, aoExpirar: sessaoExpirou });

  /** Com sessão em mãos, decide entre a escolha de temas e o feed. */
  const carregarConteudo = useCallback(async () => {
    try {
      // A tela de escolha só aparece a quem nunca escolheu. Quem decidiu não
      // marcar nada não pode ser reapresentado a ela toda visita — daí o
      // marcador ser "já escolheu", e não "tem temas".
      const temas = await buscarMeusTemas();

      // QUEM VEIO POR UM LINK DE DESTAQUE VAI PARA O DESTAQUE, mesmo sendo a
      // primeira visita.
      //
      // O link do digest abre FORA do iframe (é um clique no cliente de
      // e-mail), então o handshake com a Waid é impossível e o médico costuma
      // passar pelo login por código antes de chegar aqui. Sem esta checagem,
      // `/artigo/153` sobrevivia na barra de endereços mas era ignorado: ele
      // digitava o código e caía no feed genérico, tendo de procurar de novo o
      // destaque que tinha escolhido ler. Era o passo que faltava para o link
      // do e-mail funcionar de ponta a ponta.
      //
      // A escolha de temas não se perde: ela continua acessível pelo próprio
      // feed, e volta a aparecer sozinha na próxima visita sem link.
      if (temEntradaDireta()) {
        setEstado({ fase: 'feed' });
        return;
      }

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
    waidOrigin: ORIGENS_WAID,
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

    if (temIframe()) {
      // DENTRO do iframe e sem identidade confirmada: a sessão que estava neste
      // navegador pode ser de quem usou a máquina antes. Não se herda.
      //
      // `temIframe()`, e não "erro diferente de `sem_iframe`": desde 22/09 a
      // ponte da Waid responde no app nativo, que então cai em `timeout` quando
      // a Waid demora — e a regra antiga apagava ali o login por e-mail de um
      // aparelho pessoal.
      descartarSessaoDesteNavegador();
      pedirLogin();
      return;
    }

    // Fora de iframe — o aplicativo da Waid (com ou sem ponte) ou a URL direta,
    // aparelho pessoal. Se o login por e-mail de antes ainda vale, é ele que
    // entra; só pede código de novo quando a sessão venceu.
    if (!getToken() || isTokenExpired()) {
      clearToken();
      pedirLogin();
      return;
    }
    buscarMeusTemas()
      // Mesma regra de `carregarConteudo`: link de destaque manda no destino.
      .then(temas => setEstado(
        temEntradaDireta() || temas.ja_escolheu
          ? { fase: 'feed' }
          : { fase: 'temas', primeiraVez: true },
      ))
      .catch(() => {
        // O servidor recusou (sessão revogada por um "Sair" em outro lugar).
        clearToken();
        pedirLogin();
      });
  }, [identidade.fase, identidade.erro]);

  if (estado.fase === 'carregando') {
    // Mesma tela de espera do chat e das calculadoras. Enquanto a Waid não
    // respondeu, diz que está confirmando quem é o médico; depois, que está
    // buscando as notícias dele.
    const esperandoWaid = identidade.fase === 'pedindo' || identidade.fase === 'trocando';
    return <TelaDeEspera mensagem={esperandoWaid ? mensagemDaIdentidade(identidade.fase) : 'Carregando suas notícias…'} />;
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

  // A ROTA SÓ DECIDE O QUE MOSTRAR DEPOIS DA SESSÃO.
  //
  // Tudo acima (handshake, login, carregamento) acontece antes e fora do
  // roteador, de propósito: se `/artigo/153` fosse uma rota que qualquer um
  // alcança, o link do e-mail entraria direto no conteúdo sem passar pela
  // autenticação. O que a URL faz é escolher entre feed, artigo e temas — não
  // dar acesso.
  //
  // `primeiraVez` continua vindo do ESTADO, não da URL: é o backend que diz se
  // a pessoa já escolheu temas alguma vez, e isso não é endereçável.
  const conteudo = estado.fase === 'temas'
    ? (
      <TemasPage
        primeiraVez={estado.primeiraVez}
        aoConcluir={() => setEstado({ fase: 'feed' })}
        // Sair sem salvar so faz sentido para quem ja tem um feed para voltar.
        aoCancelar={estado.primeiraVez ? undefined : () => setEstado({ fase: 'feed' })}
      />
    )
    : <Rotas aoEditarTemas={() => setEstado({ fase: 'temas', primeiraVez: false })} />;

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

/**
 * As rotas do app, todas atrás da sessão (ver o comentário em `conteudo`).
 *
 *   /                -> feed
 *   /artigo/:id      -> feed com aquele destaque aberto
 *   /preferencias    -> tela de temas (é o link de descadastro do e-mail)
 *   qualquer outra   -> feed, sem 404
 *
 * Não há 404 de propósito: o único jeito de chegar num caminho estranho aqui é
 * por link antigo de e-mail, e mandar o médico para o feed é melhor do que
 * mostrar um erro por um endereço que nós mesmos mudamos.
 */
function Rotas({ aoEditarTemas }: { aoEditarTemas: () => void }) {
  const navegar = useNavigate();
  const feed = (artigo: number | null) => (
    <HighlightsMagazine
      aoEditarTemas={aoEditarTemas}
      artigoInicial={artigo}
      // `replace` para o "voltar" do navegador sair do app em vez de reabrir o
      // modal que a pessoa acabou de fechar.
      aoFecharArtigo={() => navegar('/', { replace: true })}
    />
  );

  return (
    <Routes>
      <Route path="/artigo/:id" element={<Artigo>{feed}</Artigo>} />
      <Route path="/preferencias" element={<AbrirTemas aoEditarTemas={aoEditarTemas} />} />
      <Route path="*" element={feed(null)} />
    </Routes>
  );
}

/** Lê o `:id` da URL. Id não numérico cai no feed, em vez de quebrar. */
function Artigo({ children }: { children: (artigo: number | null) => React.ReactNode }) {
  const { id } = useParams();
  const numero = Number(id);
  return <>{children(Number.isInteger(numero) && numero > 0 ? numero : null)}</>;
}

/**
 * `/preferencias` não renderiza nada próprio: manda o app para a fase de temas,
 * que é onde a tela vive. Efeito e não chamada direta no corpo, senão seria um
 * setState durante o render do pai.
 */
function AbrirTemas({ aoEditarTemas }: { aoEditarTemas: () => void }) {
  useEffect(() => {
    aoEditarTemas();
  }, [aoEditarTemas]);
  return <div style={aviso}>Abrindo suas preferências…</div>;
}

const aviso: React.CSSProperties = {
  padding: 48,
  textAlign: 'center',
  fontFamily: "var(--m360-font, 'Just Sans', -apple-system, 'Segoe UI', sans-serif)",
  color: '#014751',
};
