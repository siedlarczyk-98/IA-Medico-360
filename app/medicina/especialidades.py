"""
Vocabulário canônico de especialidades médicas.

⚠️  ESTE ARQUIVO É O PRODUTO, NÃO INFRAESTRUTURA — no mesmo sentido de
`app/news/taxonomia.py`. Um nome errado aqui não quebra teste nenhum: só faz o
médico receber conteúdo que não é dele.

POR QUE ELE EXISTE
Até agora a lista canônica de especialidades morava num arquivo TSX
(`frontend-app/src/pages/OnboardingPage.tsx`), a ponto de
`tests/test_news_taxonomia.py` precisar LER O TSX COM REGEX para validar o
backend. E havia três listas divergentes no repo:

  1. o TSX (55 nomes CFM completos)  -> é o que está gravado em `users.specialty`
  2. `app/services/specialty_detector.py` (31 nomes curtos, incompatíveis)
  3. a tabela `calculators.specialties` (3 slugs)

A (1) foi eleita canônica não por ser a melhor, mas porque `users.specialty` e
`news.topic_specialties.specialty` JÁ contêm exatamente essas strings em
produção. Eleger outra custaria uma migração de dados em duas tabelas para
ganhar nada. A (2) entra aqui como `aliases`; a (3) fica como está por ora.

O QUE É `slug` E O QUE É `nome`
  - `slug`  — a CHAVE. Estável, sem acento, é por ela que se consulta e agrupa.
  - `nome`  — o RÓTULO. É o que aparece na tela e o que casa por string com
              `news.topic_specialties.specialty`. Mudar um `nome` quebra o feed
              de notícias de quem tem aquela especialidade; mudar exige migração.

PARA QUE SERVEM OS `aliases`
São o amortecedor entre o mundo de fora e o nosso vocabulário. Entram aqui:
  - os nomes curtos do detector ("Ortopedia" -> Ortopedia e Traumatologia);
  - os nomes dos GRUPOS DE ACESSO da WAID/Curseduca, que são artefatos de
    controle de acesso e não campos de especialidade — se alguém renomear um
    grupo no painel, é aqui que se conserta, sem tocar em código;
  - grafias alternativas que aparecerem no cadastro da página intermediária.

A comparação já é insensível a acento, caixa e espaço — não gaste alias com
isso. Alias é para nome REALMENTE diferente.
"""

import unicodedata
from dataclasses import dataclass, field

# O generalista sem especialidade declarada cai aqui. Existe porque o SSO de
# embed cria usuário só com e-mail, e porque generalista/graduando nunca foram
# perguntados no onboarding. Ver `app/services/news_feed_service.py`.
ESPECIALIDADE_GENERALISTA = "clinica-medica"


@dataclass(frozen=True)
class Especialidade:
    slug: str
    nome: str
    # Nomes alternativos que devem resolver para esta especialidade.
    aliases: tuple[str, ...] = field(default=())
    # Entra na lista fechada do prompt do classificador de perguntas
    # (`specialty_detector`). Subconjunto de propósito: mandar as 55 infla o
    # prompt de cada pergunta sem melhorar a classificação.
    detector: bool = False


ESPECIALIDADES: tuple[Especialidade, ...] = (
    Especialidade("acupuntura", "Acupuntura"),
    Especialidade("alergia-e-imunologia", "Alergia e Imunologia", detector=True),
    Especialidade("anestesiologia", "Anestesiologia"),
    Especialidade("angiologia", "Angiologia", detector=True),
    Especialidade("cardiologia", "Cardiologia", detector=True),
    Especialidade("cirurgia-cardiovascular", "Cirurgia Cardiovascular"),
    Especialidade("cirurgia-da-mao", "Cirurgia da Mão"),
    Especialidade("cirurgia-de-cabeca-e-pescoco", "Cirurgia de Cabeça e Pescoço"),
    Especialidade("cirurgia-do-aparelho-digestivo", "Cirurgia do Aparelho Digestivo"),
    Especialidade("cirurgia-geral", "Cirurgia Geral", aliases=("Cirurgia",), detector=True),
    Especialidade("cirurgia-oncologica", "Cirurgia Oncológica"),
    Especialidade("cirurgia-pediatrica", "Cirurgia Pediátrica"),
    Especialidade("cirurgia-plastica", "Cirurgia Plástica"),
    Especialidade("cirurgia-toracica", "Cirurgia Torácica"),
    Especialidade("cirurgia-vascular", "Cirurgia Vascular"),
    Especialidade(
        "clinica-medica",
        "Clínica Médica",
        aliases=("Clínica Geral", "Medicina Interna"),
        detector=True,
    ),
    Especialidade("coloproctologia", "Coloproctologia", detector=True),
    Especialidade("dermatologia", "Dermatologia", detector=True),
    Especialidade(
        "endocrinologia-e-metabologia",
        "Endocrinologia e Metabologia",
        aliases=("Endocrinologia",),
        detector=True,
    ),
    Especialidade("endoscopia", "Endoscopia"),
    Especialidade("gastroenterologia", "Gastroenterologia", detector=True),
    Especialidade("genetica-medica", "Genética Médica"),
    Especialidade("geriatria", "Geriatria", detector=True),
    Especialidade(
        "ginecologia-e-obstetricia",
        "Ginecologia e Obstetrícia",
        # As duas metades chegam separadas do detector e, provavelmente, dos
        # grupos da WAID. Ambas resolvem para a especialidade única do CFM.
        aliases=("Ginecologia", "Obstetrícia", "GO"),
        detector=True,
    ),
    Especialidade(
        "hematologia-e-hemoterapia",
        "Hematologia e Hemoterapia",
        aliases=("Hematologia",),
        detector=True,
    ),
    Especialidade("homeopatia", "Homeopatia"),
    Especialidade("infectologia", "Infectologia", detector=True),
    Especialidade("mastologia", "Mastologia", detector=True),
    Especialidade("medicina-de-emergencia", "Medicina de Emergência", detector=True),
    Especialidade("medicina-de-familia-e-comunidade", "Medicina de Família e Comunidade"),
    Especialidade(
        "medicina-do-esporte",
        "Medicina do Esporte",
        aliases=("Medicina Esportiva",),
        detector=True,
    ),
    Especialidade("medicina-do-trabalho", "Medicina do Trabalho", detector=True),
    Especialidade("medicina-do-trafego", "Medicina do Tráfego"),
    Especialidade("medicina-fisica-e-reabilitacao", "Medicina Física e Reabilitação"),
    Especialidade("medicina-intensiva", "Medicina Intensiva"),
    Especialidade("medicina-legal-e-pericia-medica", "Medicina Legal e Perícia Médica"),
    Especialidade("medicina-nuclear", "Medicina Nuclear"),
    Especialidade("medicina-preventiva-e-social", "Medicina Preventiva e Social"),
    Especialidade("nefrologia", "Nefrologia", detector=True),
    Especialidade("neurocirurgia", "Neurocirurgia"),
    Especialidade("neurologia", "Neurologia", detector=True),
    Especialidade("nutrologia", "Nutrologia", detector=True),
    Especialidade("oftalmologia", "Oftalmologia", detector=True),
    Especialidade(
        "oncologia-clinica", "Oncologia Clínica", aliases=("Oncologia",), detector=True
    ),
    Especialidade(
        "ortopedia-e-traumatologia",
        "Ortopedia e Traumatologia",
        aliases=("Ortopedia", "Traumatologia"),
        detector=True,
    ),
    Especialidade("otorrinolaringologia", "Otorrinolaringologia", detector=True),
    Especialidade("patologia", "Patologia"),
    Especialidade(
        "patologia-clinica-medicina-laboratorial",
        "Patologia Clínica/Medicina Laboratorial",
        aliases=("Patologia Clínica", "Medicina Laboratorial"),
    ),
    Especialidade("pediatria", "Pediatria", detector=True),
    Especialidade("pneumologia", "Pneumologia", detector=True),
    Especialidade("psiquiatria", "Psiquiatria", detector=True),
    Especialidade(
        "radiologia-e-diagnostico-por-imagem",
        "Radiologia e Diagnóstico por Imagem",
        aliases=("Radiologia", "Diagnóstico por Imagem"),
        detector=True,
    ),
    Especialidade("radioterapia", "Radioterapia"),
    Especialidade("reumatologia", "Reumatologia", detector=True),
    Especialidade("urologia", "Urologia", detector=True),
)


def _chave(texto: str) -> str:
    """Forma comparável: sem acento, sem caixa, sem espaço redundante.

    É o que dispensa alias para variação boba de digitação. `unicodedata.NFKD`
    separa a letra do acento e o filtro descarta os acentos isolados.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.casefold().split())


def _construir_indice() -> dict[str, str]:
    """Mapa `chave comparável -> slug`, montado uma vez no import.

    Colisão aqui é erro de programação (dois nomes/aliases resolvendo para
    especialidades diferentes), não condição de runtime: falha no import, que é
    quando alguém ainda pode consertar. `tests/test_especialidades.py` cobre.
    """
    indice: dict[str, str] = {}

    def registrar(texto: str, slug: str) -> None:
        chave = _chave(texto)
        anterior = indice.get(chave)
        if anterior is not None and anterior != slug:
            raise ValueError(
                f"Ambiguidade no vocabulário: '{texto}' resolve para "
                f"'{anterior}' e para '{slug}'"
            )
        indice[chave] = slug

    for esp in ESPECIALIDADES:
        registrar(esp.slug, esp.slug)
        registrar(esp.nome, esp.slug)
        for alias in esp.aliases:
            registrar(alias, esp.slug)
    return indice


_INDICE: dict[str, str] = _construir_indice()
_POR_SLUG: dict[str, Especialidade] = {e.slug: e for e in ESPECIALIDADES}


def normalizar(texto: str | None) -> str | None:
    """Resolve qualquer grafia conhecida para o slug canônico. `None` se não reconhecer.

    NÃO tenta adivinhar (nada de fuzzy match): um palpite errado grava a
    especialidade errada em silêncio, que é pior do que não gravar. Texto não
    reconhecido vira `None` e o chamador decide — em geral, preservar o original
    e registrar para virar alias depois.
    """
    if not texto:
        return None
    return _INDICE.get(_chave(texto))


def por_slug(slug: str | None) -> Especialidade | None:
    return _POR_SLUG.get(slug) if slug else None


# ── Grupos de acesso da WAID/Curseduca ────────────────────────────────────

# A página de cadastro cria os grupos AUTOMATICAMENTE, um por especialidade,
# no formato "[CFM] Alergia e Imunologia". O prefixo é o que separa o grupo de
# especialidade dos demais (turma, produto, campanha) — o membro está em vários.
PREFIXO_GRUPO_CFM = "[cfm]"


@dataclass(frozen=True)
class GrupoCFM:
    """Um grupo de especialidade da WAID, já interpretado.

    `slug is None` NÃO é o mesmo que "não é grupo de especialidade": significa
    que é um, mas o vocabulário não o reconhece. Distinção que importa porque os
    grupos nascem sozinhos — o candidato mais provável é uma ÁREA DE ATUAÇÃO do
    CFM (Ecocardiografia, Hepatologia, Medicina Paliativa), que não é
    especialidade e não está nas 55. Quem chama deve logar em WARNING: sem isso
    o médico fica sem especialidade em silêncio, que é o modo de falha que este
    trabalho inteiro veio eliminar.
    """

    rotulo: str
    slug: str | None


def de_grupo_cfm(nome_do_grupo: str | None) -> GrupoCFM | None:
    """Interpreta o nome de um grupo da WAID. `None` se não for de especialidade."""
    if not nome_do_grupo:
        return None
    texto = nome_do_grupo.strip()
    if not texto[: len(PREFIXO_GRUPO_CFM)].casefold() == PREFIXO_GRUPO_CFM:
        return None
    rotulo = texto[len(PREFIXO_GRUPO_CFM) :].strip()
    if not rotulo:
        return None
    return GrupoCFM(rotulo=rotulo, slug=normalizar(rotulo))


# Especialidades de PRÉ-REQUISITO: quase todo especialista clínico tem Clínica
# Médica e quase todo cirurgião tem Cirurgia Geral, porque são os R1-R2 exigidos
# antes da residência da área. Entre elas e qualquer outra, a outra é o que a
# pessoa de fato exerce — e é o que deve aparecer na tela e no prompt.
SLUGS_PRE_REQUISITO = frozenset({"clinica-medica", "cirurgia-geral"})


# O cadastro cria `[CFM] GENERALISTA` quando o CFM não devolve especialidade
# nenhuma para aquele CRM. É um rótulo CONHECIDO, não uma lacuna do vocabulário:
# sem esta constante ele cairia em `desconhecidos` e dispararia o alerta de
# "área de atuação não mapeada" para todo generalista da base.
#
# E NÃO vira alias de Clínica Médica. Clínica Médica é especialidade real, com
# RQE; escrevê-la para quem o Conselho diz não ter nenhuma seria afirmar um
# registro inexistente — num campo que tem proveniência, trilha de auditoria e
# vai definir acesso a conteúdo pago. O generalista continua com `specialty`
# NULL, que é a verdade. Para CONTEÚDO, quem resolve é o
# `ESPECIALIDADE_PISO` do feed de notícias: coisas diferentes, camadas
# diferentes.
ROTULO_GENERALISTA = "generalista"


@dataclass(frozen=True)
class GruposDoMembro:
    """O que os grupos `[CFM]` de um membro dizem sobre ele.

    `slugs` é a resposta completa e é a que vale para FEED e ACESSO: um médico
    com duas residências tem direito às duas, e colapsar isso num campo só
    revogaria acesso em silêncio.

    `principal` existe só para exibição e para o sufixo do prompt, que pedem uma
    resposta única. É derivada, não uma escolha sobre o que a pessoa é.

    `generalista` é o `[CFM] GENERALISTA`: o CFM foi consultado e não devolveu
    especialidade. É informação POSITIVA, e diferente de "nenhum grupo `[CFM]`"
    — esta última só diz que não sabemos se alguém chegou a consultar.

    `desconhecidos` são rótulos `[CFM]` que o vocabulário não reconhece — em
    geral área de atuação do CFM (Hepatologia, Medicina Paliativa). Quem chama
    loga em WARNING.
    """

    slugs: tuple[str, ...]
    desconhecidos: tuple[str, ...]
    generalista: bool = False

    @property
    def principal(self) -> str | None:
        if not self.slugs:
            return None
        # Ordem alfabética antes de tudo: desempate arbitrário, mas
        # DETERMINÍSTICO. Sem isto a principal dependeria da ordem em que a API
        # devolveu os grupos, e mudaria sozinha entre um login e outro.
        em_ordem = sorted(self.slugs)
        exercidas = [s for s in em_ordem if s not in SLUGS_PRE_REQUISITO]
        return exercidas[0] if exercidas else em_ordem[0]


def interpretar_grupos(nomes_de_grupos) -> GruposDoMembro:
    """Lê todos os grupos de um membro e separa o que usar, o que ignorar e o que alertar."""
    reconhecidos: list[str] = []
    desconhecidos: list[str] = []
    generalista = False
    for nome in nomes_de_grupos or ():
        grupo = de_grupo_cfm(nome)
        if grupo is None:
            continue
        if _chave(grupo.rotulo) == ROTULO_GENERALISTA:
            generalista = True
        elif grupo.slug is None:
            desconhecidos.append(grupo.rotulo)
        elif grupo.slug not in reconhecidos:
            reconhecidos.append(grupo.slug)
    return GruposDoMembro(tuple(reconhecidos), tuple(desconhecidos), generalista)


def nome_de(slug: str | None) -> str | None:
    esp = por_slug(slug)
    return esp.nome if esp else None


def slugs() -> set[str]:
    return set(_POR_SLUG)


def nomes_canonicos() -> set[str]:
    return {e.nome for e in ESPECIALIDADES}


def para_api() -> list[dict[str, str]]:
    """Payload de `GET /api/v1/meta/especialidades`, em ordem alfabética de rótulo."""
    return [{"slug": e.slug, "nome": e.nome} for e in sorted(ESPECIALIDADES, key=lambda e: e.nome)]


def nomes_para_detector() -> list[str]:
    """Lista fechada que vai no prompt do classificador de perguntas."""
    return [e.nome for e in ESPECIALIDADES if e.detector]
