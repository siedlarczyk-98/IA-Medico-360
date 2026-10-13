"""
De onde a pessoa veio e o que ela é, lido dos grupos de acesso da Waid.

Duas portas de entrada dão acesso ao Médico 360 hoje, e cada uma deixa um
grupo com prefixo próprio no membro:

  `[CFM] <especialidade>`   — a página de cadastro consultou o CRM no Conselho
                              e criou o grupo. Prova que há CRM.
  `[Cursos Active] <perfil> - <curso>`
                            — a integração do site dos cursos presenciais
                              (ACLS, PALS, BLS...) criou o membro ao vender o
                              curso. NÃO passa pela consulta ao CFM; o que o
                              grupo diz é o perfil informado na compra:
                              "Médico(a)", "Estudante 6º Medicina",
                              "Enfermeiro(a)", "Estudantes 5º Enfermagem",
                              "Profissionais de saúde".

Quem não tem nenhum dos dois (força de vendas, áreas de laboratório) não é
usuário do Médico 360 para efeito de contagem — decisão do Ruben em 2026-10-13.

Este módulo é puro: recebe nomes de grupo, devolve rótulos. Quem grava é o login
(`auth_service`) e a sincronização diária (`membros_waid_service`), e os dois
usam ESTA leitura — senão o mesmo membro teria canal diferente em cada tabela.
"""

import unicodedata

from app.medicina.especialidades import PREFIXO_GRUPO_CFM

PREFIXO_CURSOS_ACTIVE = "[cursos active]"

CANAL_CURSOS_ACTIVE = "cursos_active"
CANAL_CADASTRO_CFM = "cadastro_cfm"

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


def _tem_prefixo(nome: str, prefixo: str) -> bool:
    return _chave(nome).startswith(prefixo)


def e_grupo_cfm(nome: str | None) -> bool:
    return bool(nome) and _tem_prefixo(nome, PREFIXO_GRUPO_CFM)


def e_grupo_cursos_active(nome: str | None) -> bool:
    return bool(nome) and _tem_prefixo(nome, PREFIXO_CURSOS_ACTIVE)


def grupos_do_medico360(nomes) -> list[str]:
    """Só os grupos que contam: `[CFM]` e `[Cursos Active]`, em ordem estável."""
    return sorted({n for n in nomes or () if e_grupo_cfm(n) or e_grupo_cursos_active(n)})


def canal_de_entrada(nomes) -> str | None:
    """Por qual porta a pessoa entrou. `None` se por nenhuma das duas.

    Cursos Active ganha do CFM: quem comprou um curso presencial e DEPOIS passou
    pela página de cadastro entrou pelo curso. A página de cadastro, por sua vez,
    não cria grupo `[Cursos Active]`, então a recíproca não acontece.
    """
    nomes = list(nomes or ())
    if any(e_grupo_cursos_active(n) for n in nomes):
        return CANAL_CURSOS_ACTIVE
    if any(e_grupo_cfm(n) for n in nomes):
        return CANAL_CADASTRO_CFM
    return None


def _profissao_de_grupo(nome: str) -> str | None:
    if e_grupo_cfm(nome):
        return PROFISSAO_MEDICO
    if not e_grupo_cursos_active(nome):
        return None
    # "[Cursos Active] Estudante 6º Medicina - ACLS" -> "estudante 6o medicina"
    perfil = _chave(nome)[len(PREFIXO_CURSOS_ACTIVE):].split(" - ")[0]
    if "estudante" in perfil and "enfermagem" in perfil:
        return PROFISSAO_ESTUDANTE_ENFERMAGEM
    if "estudante" in perfil:
        return PROFISSAO_ESTUDANTE_MEDICINA
    if "enferm" in perfil:
        return PROFISSAO_ENFERMEIRO
    if "medic" in perfil:
        return PROFISSAO_MEDICO
    if "profissionais de saude" in perfil or "profissional de saude" in perfil:
        return PROFISSAO_SAUDE
    return None


def profissao(nomes) -> str | None:
    """A profissão que os grupos indicam, ou `None` se nenhum grupo diz."""
    achadas = {p for p in (_profissao_de_grupo(n) for n in nomes or () if n) if p}
    return next((p for p in _PRECEDENCIA_PROFISSAO if p in achadas), None)
