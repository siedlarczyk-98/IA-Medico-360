"""
De onde a pessoa veio e o que ela é, lido dos grupos de acesso da Waid.

As regras são do Ruben (2026-10-13). Só três prefixos de grupo fazem alguém
contar como usuário do Médico 360:

  `[Cursos Active] <perfil> - <curso>`
      A integração do site dos cursos presenciais (ACLS, PALS...) criou o membro
      ao vender o curso. Canal "Cursos Active".
  `[CFM] <especialidade>`
      A LP de cadastro consultou o CRM no Conselho. Prova que é médico.
  `[ONBOARDING] - <categoria>`
      A mesma LP, para quem não tem CRM (estudante, enfermeiro...).

`[CFM]` e `[ONBOARDING]` NÃO dizem por qual porta a pessoa entrou: a consulta
ao CRM roda também no cadastro dos programas das farmacêuticas, que dividem a
mesma Waid em outros "andares" (áreas de membros). Por isso:

  - tem `[CFM]`/`[ONBOARDING]` e acesso a um andar de farmacêutica -> "Usuário Immerso"
  - tem `[CFM]`/`[ONBOARDING]` e nenhum andar de farmacêutica      -> "LP do Médico 360"

Quem não tem nenhum dos três prefixos não conta, nunca — nem se abrir a IA.

O andar vem da Waid (`GET /reports/groups`, campo `tenants`) e quem decide é a
sincronização diária (`membros_waid_service`). O login só guarda os grupos e a
profissão; o canal ele não sabe, porque o payload do membro não traz os andares.
"""

import unicodedata

from app.medicina.especialidades import PREFIXO_GRUPO_CFM

PREFIXO_CURSOS_ACTIVE = "[cursos active]"
PREFIXO_ONBOARDING = "[onboarding]"

CANAL_CURSOS_ACTIVE = "cursos_active"
CANAL_LP_MEDICO360 = "lp_medico360"
CANAL_IMMERSO = "immerso"

# Andares (áreas de membros da Waid) de farmacêutica, pelo uuid — o nome pode
# ser renomeado no painel, o uuid não. Lista conferida em 2026-10-13 com
# `list_member_areas`. Médico 360, Área de parceiros, Aplicativo e SBC NÃO são
# farmacêutica. Andar novo de farmacêutica precisa entrar aqui.
ANDARES_FARMACEUTICA = {
    "60f3263a-f1a7-4cc8-b8d8-3e48597d1b1e": "Pfizer",
    "b361cac9-1d53-4154-944a-77a599944283": "ST-ATTRs - Vitrine dedicada",
    "6cb0c326-3bd1-481f-abde-952022103154": "Pfizer - Força de Vendas",
    "c1f519e4-db6b-45a0-a240-3a16e6291cff": "Pfizer - IOA",
    "210f8fb9-a6ae-43c3-813b-22955390a2a1": "AstraZeneca - Força de vendas",
    "d1fce8b6-2b39-4009-bc97-581bf73cd157": "Lilly",
    "ce2af619-4a4c-4834-ad71-f4765e55acb2": "Novartis",
    "f7c9b08b-db90-476b-9628-5338a1b1abcf": "Demo Força de Vendas Immerso",
}

PROFISSAO_MEDICO = "medico"
PROFISSAO_ESTUDANTE_MEDICINA = "estudante_medicina"
PROFISSAO_ENFERMEIRO = "enfermeiro"
PROFISSAO_ESTUDANTE_ENFERMAGEM = "estudante_enfermagem"
PROFISSAO_SAUDE = "profissional_saude"

# Quando o membro está em mais de um grupo, vale o que diz MAIS sobre ele:
# o estudante que se forma ganha o grupo de médico e continua no antigo, e
# "profissional de saúde" (BLS) é o rótulo mais genérico de todos.
_PRECEDENCIA_PROFISSAO = (
    PROFISSAO_MEDICO,
    PROFISSAO_ENFERMEIRO,
    PROFISSAO_ESTUDANTE_MEDICINA,
    PROFISSAO_ESTUDANTE_ENFERMAGEM,
    PROFISSAO_SAUDE,
)


def _chave(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.casefold().split())


def _tem_prefixo(nome: str | None, prefixo: str) -> bool:
    return bool(nome) and _chave(nome).startswith(prefixo)


def e_grupo_cfm(nome: str | None) -> bool:
    return _tem_prefixo(nome, PREFIXO_GRUPO_CFM)


def e_grupo_cursos_active(nome: str | None) -> bool:
    return _tem_prefixo(nome, PREFIXO_CURSOS_ACTIVE)


def e_grupo_onboarding(nome: str | None) -> bool:
    return _tem_prefixo(nome, PREFIXO_ONBOARDING)


def e_grupo_que_conta(nome: str | None) -> bool:
    return e_grupo_cursos_active(nome) or e_grupo_cfm(nome) or e_grupo_onboarding(nome)


def grupos_do_medico360(nomes) -> list[str]:
    """Só os grupos que contam, em ordem estável."""
    return sorted({n for n in nomes or () if e_grupo_que_conta(n)})


def e_andar_de_farmaceutica(andar: dict | None) -> bool:
    return isinstance(andar, dict) and str(andar.get("uuid") or "") in ANDARES_FARMACEUTICA


def canal_de_entrada(nomes, *, em_andar_de_farmaceutica: bool) -> str | None:
    """Por qual porta a pessoa entrou. `None` = não conta como usuário.

    Cursos Active ganha de tudo: a integração do curso presencial é inequívoca,
    e quem comprou o curso e depois passou pela LP entrou pelo curso.
    """
    nomes = list(nomes or ())
    if any(e_grupo_cursos_active(n) for n in nomes):
        return CANAL_CURSOS_ACTIVE
    if any(e_grupo_cfm(n) or e_grupo_onboarding(n) for n in nomes):
        return CANAL_IMMERSO if em_andar_de_farmaceutica else CANAL_LP_MEDICO360
    return None


def _perfil_do_texto(perfil: str) -> str | None:
    if "estudante" in perfil and "enfermagem" in perfil:
        return PROFISSAO_ESTUDANTE_ENFERMAGEM
    if "estudante" in perfil or "aluno" in perfil:
        return PROFISSAO_ESTUDANTE_MEDICINA
    if "enferm" in perfil:
        return PROFISSAO_ENFERMEIRO
    if "medic" in perfil:
        return PROFISSAO_MEDICO
    if "profissiona" in perfil and "saude" in perfil:
        return PROFISSAO_SAUDE
    return None


def _profissao_de_grupo(nome: str) -> str | None:
    if e_grupo_cfm(nome):
        return PROFISSAO_MEDICO
    chave = _chave(nome)
    if e_grupo_cursos_active(nome):
        # "[cursos active] estudante 6o medicina - acls" -> "estudante 6o medicina"
        return _perfil_do_texto(chave[len(PREFIXO_CURSOS_ACTIVE):].split(" - ")[0])
    if e_grupo_onboarding(nome):
        # "[onboarding] - medico(a)" -> "medico(a)"
        return _perfil_do_texto(chave[len(PREFIXO_ONBOARDING):].lstrip(" -"))
    return None


def profissao(nomes) -> str | None:
    """A profissão que os grupos indicam, ou `None` se nenhum grupo diz."""
    achadas = {p for p in (_profissao_de_grupo(n) for n in nomes or () if n) if p}
    return next((p for p in _PRECEDENCIA_PROFISSAO if p in achadas), None)
