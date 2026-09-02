"""
Identidade profissional do usuário: quem pode escrever a especialidade, e o que
ainda falta no perfil.

Este módulo é O CONTRATO. Ele existe porque a especialidade passa a chegar por
quatro caminhos diferentes, em qualquer ordem, repetidas vezes:

  `declarado`  — o próprio médico digitou no onboarding. FALLBACK, não verdade:
                 vale só enquanto nenhuma fonte automática chegou.
  `waid_grupo` — reconciliação a partir do nome do grupo de acesso da Curseduca,
                 lido de graça no payload que o embed já baixa a cada login.
  `cfm`        — verificação contra o Conselho, que também traz o RQE.
  `cadastro`   — webhook da página de cadastro intermediária. É o registro
                 COMERCIAL: o que o médico de fato preencheu e contratou.
  `admin`      — correção manual pelo suporte. Ganha de tudo, e de propósito.

Sem uma regra única, o último a escrever ganha — e a reconciliação do login
seguinte desfaria em silêncio o que o webhook acabou de gravar.

A PRECEDÊNCIA
    admin  >  cadastro  >  cfm  >  waid_grupo  >  declarado

POR QUE `declarado` FICA NO FUNDO (e não no topo, como no primeiro desenho)
Porque `users.specialty` não é preferência de leitura — é IDENTIDADE
PROFISSIONAL, e vai passar a definir ACESSO a conteúdo pago (o grupo da WAID é
um grupo de acesso: reflete o que a pessoa contratou). Se o médico pudesse
reescrever esse campo pelo app, ele alcançaria conteúdo de outro produto
digitando um nome diferente numa caixa de seleção.

O que o médico ajusta livremente é OUTRA coisa, e já existe: `news.user_topics`.
A especialidade só pré-marca as caixas; a partir daí ele escolhe o que lê. Ou
seja, travar este campo não prende ninguém a conteúdo errado — prende ao próprio
registro profissional, que é exatamente o que deve ser imutável.

`cadastro` ganha do `cfm` pela mesma razão: o Conselho é autoridade sobre o
REGISTRO, mas o direito de acesso vem do que foi contratado, não do RQE.

CORREÇÃO (LGPD art. 18, III)
O titular tem direito a corrigir dado pessoal desatualizado, então o bloqueio é
de TELA, não de banco: o médico não edita, mas o suporte edita (fonte `admin`) e
o conserto na origem reflete via webhook. Sem essa saída, o campo seria
juridicamente indefensável.

REGRA DE OURO
Todo caminho de escrita de `users.specialty` passa por `aplicar_especialidade`.
Se existir um segundo lugar que atribui `user.specialty = ...` direto, a
precedência já morreu e este arquivo virou decoração.
"""

from datetime import UTC, datetime

from app.medicina import especialidades

# ── Fontes, em ordem crescente de autoridade ──────────────────────────────

FONTE_DECLARADO = "declarado"
FONTE_WAID_GRUPO = "waid_grupo"
FONTE_CFM = "cfm"
FONTE_CADASTRO = "cadastro"
FONTE_ADMIN = "admin"

_POSTO: dict[str, int] = {
    FONTE_DECLARADO: 1,
    FONTE_WAID_GRUPO: 2,
    FONTE_CFM: 3,
    FONTE_CADASTRO: 4,
    FONTE_ADMIN: 5,
}

FONTES = frozenset(_POSTO)

# Fontes que o próprio médico consegue produzir pelo app. Tudo fora daqui é
# automático ou administrativo, e tranca a edição no perfil.
FONTES_DO_USUARIO = frozenset({FONTE_DECLARADO})


def _posto(fonte: str | None) -> int:
    """Campo nunca preenchido tem posto 0 — qualquer fonte escreve por cima.

    Fonte desconhecida (dado antigo, valor escrito à mão no banco) também vale 0:
    é melhor deixar uma fonte legítima corrigir do que travar o registro para
    sempre por causa de uma string que ninguém reconhece.
    """
    return _POSTO.get(fonte or "", 0)


def pode_escrever(fonte: str, fonte_atual: str | None) -> bool:
    """Empate escreve (`>=`), de propósito: permite a mesma fonte se atualizar."""
    if fonte not in FONTES:
        raise ValueError(f"Fonte desconhecida: {fonte!r}. Use uma de {sorted(FONTES)}.")
    return _posto(fonte) >= _posto(fonte_atual)


def aplicar_especialidade(
    user,
    *,
    slug: str | None = None,
    slugs: list[str] | tuple[str, ...] | None = None,
    fonte: str,
    rqe: str | None = None,
    agora: datetime | None = None,
) -> bool:
    """Grava a(s) especialidade(s) se a `fonte` tiver autoridade para isso.

    Passe `slugs` quando a fonte souber de todas (duas residências é o caso
    comum) e `slug` quando souber de uma só. A principal é derivada da lista por
    `GruposDoMembro.principal` — Clínica Médica e Cirurgia Geral perdem para
    qualquer outra, porque são pré-requisito e não o que a pessoa exerce.

    Retorna True se algo mudou no objeto. False significa "ignorado por
    precedência" OU "já estava exatamente assim" — os dois casos são não-eventos
    para quem chama, e é o que torna o webhook seguro de reenviar.

    NÃO faz commit: quem chama decide a transação.
    """
    if fonte not in FONTES:
        raise ValueError(f"Fonte desconhecida: {fonte!r}. Use uma de {sorted(FONTES)}.")

    if (slug is None) == (slugs is None):
        raise ValueError("Passe exatamente um de `slug` ou `slugs`")

    lista = list(slugs) if slugs is not None else [slug]
    if not lista:
        raise ValueError("`slugs` não pode ser vazio")

    for s in lista:
        if especialidades.por_slug(s) is None:
            # Slug inválido é erro de programação: normalize ANTES de chamar, e
            # trate o `None` do `normalizar()` como "não reconheci" no chamador.
            raise ValueError(f"Especialidade desconhecida: {s!r}")

    if not pode_escrever(fonte, getattr(user, "specialty_source", None)):
        return False

    principal = especialidades.GruposDoMembro(tuple(lista), ()).principal
    esp = especialidades.por_slug(principal)

    # Só o CFM carrega RQE: é o único que confere registro. Manter o RQE antigo
    # numa escrita de outra fonte daria selo de verificado a um dado que acabou
    # de deixar de ser verificado.
    rqe_novo = rqe if fonte == FONTE_CFM else None
    # Ordenada para que a comparação de "inalterado" não dependa da ordem em que
    # a API externa devolveu os grupos.
    todas = sorted(set(lista))

    inalterado = (
        getattr(user, "specialty_slug", None) == esp.slug
        and getattr(user, "specialty", None) == esp.nome
        and getattr(user, "specialty_source", None) == fonte
        and getattr(user, "specialty_rqe", None) == rqe_novo
        and (getattr(user, "specialties", None) or []) == todas
    )
    if inalterado:
        return False

    user.specialty_slug = esp.slug
    user.specialty = esp.nome
    user.specialties = todas
    user.specialty_source = fonte
    user.specialty_rqe = rqe_novo
    user.specialty_updated_at = agora or datetime.now(UTC)
    return True


def rotulos_de_especialidade(user) -> list[str]:
    """TODOS os rótulos do médico, para casar com `news.topic_specialties.specialty`.

    Aquela tabela casa por rótulo (string), não por slug — daí a conversão.

    Cai no `specialty` singular quando `specialties` está vazio: as linhas
    anteriores à migration 007 só têm o singular preenchido, e o backfill pode
    não ter rodado ainda. Sem esse fallback, o feed inteiro da base atual
    silenciaria de uma vez no deploy.
    """
    slugs = getattr(user, "specialties", None) or []
    rotulos = [nome for nome in (especialidades.nome_de(s) for s in slugs) if nome]
    if rotulos:
        return rotulos
    unico = getattr(user, "specialty", None)
    return [unico] if unico else []


MED_STATUS_TODOS = ("graduando", "generalista", "residente", "especialista")

# Fontes que só existem porque alguém consultou o CFM a partir de um CRM.
_FONTES_COM_CRM = frozenset({FONTE_WAID_GRUPO, FONTE_CADASTRO, FONTE_CFM})


def med_status_possiveis(user) -> list[str]:
    """Os estágios de carreira compatíveis com o que já sabemos.

    Estar num grupo `[CFM]` PROVA que o Conselho foi consultado a partir de um
    CRM — e isso elimina opções:

      especialidade registrada  -> não é graduando (não teria CRM) nem
                                   generalista (não teria especialidade)
      CRM verificado, sem espec. -> não é graduando, nem especialista (não tem RQE)

    Mostrar as quatro opções para quem está em `[CFM] Cardiologia` é pedir que
    ele responda algo que o registro dele já respondeu — e abre espaço para uma
    resposta que contradiz o Conselho.

    Não DECIDE o `med_status`: nenhuma fonte distingue residente de especialista
    (o R1 aparece no CFM sem RQE, igual ao generalista). Reduzir a escolha é
    honesto; adivinhá-la seria gravar dado errado em silêncio.
    """
    fonte = getattr(user, "specialty_source", None)

    if getattr(user, "specialty_slug", None) and fonte in _FONTES_COM_CRM:
        return ["residente", "especialista"]

    # `crm_verified_at` é marcado quando um grupo `[CFM]` aparece — inclusive o
    # `[CFM] GENERALISTA`, que é o Conselho dizendo "este CRM existe e não tem
    # especialidade". Diferente de nunca termos consultado.
    if getattr(user, "crm_verified_at", None):
        return ["generalista", "residente"]

    return list(MED_STATUS_TODOS)


def usuario_pode_editar(user) -> bool:
    """Se o MÉDICO pode trocar a própria especialidade pelo app.

    Só enquanto o valor for algo que ele mesmo digitou (`declarado`) ou não
    existir. Assim que uma fonte automática chega — cadastro, grupo da WAID,
    CFM — o campo tranca, porque a partir daí ele reflete o que foi contratado e
    verificado, não uma preferência.

    O suporte continua podendo corrigir (fonte `admin`): o bloqueio é de tela,
    não de banco. Ver a nota de LGPD no topo do arquivo.

    Vai no `/auth/me` para o front decidir se renderiza o campo como editável ou
    como texto — sem reimplementar esta regra em três apps.
    """
    fonte = getattr(user, "specialty_source", None)
    return fonte is None or fonte in FONTES_DO_USUARIO


# ── Pendências do perfil ──────────────────────────────────────────────────

PENDENCIA_NOME = "nome"
PENDENCIA_ACEITE = "aceite_termos"
PENDENCIA_MED_STATUS = "med_status"
PENDENCIA_ESPECIALIDADE = "especialidade"

# `crm` NÃO é pendência, de propósito — decisão de 2026-09-02.
#
# O CRM servia para provar que a pessoa é médica registrada, e essa prova já
# vem pronta: a página de cadastro consulta o CFM e cria o grupo
# `[CFM] <especialidade>`. O grupo É a prova. Um CRM que o próprio médico digita
# num campo, sem ninguém verificar, é uma afirmação — não acrescenta prova
# nenhuma sobre o que o grupo já disse.
#
# A coluna continua existindo e continua sendo gravada quando o dado chega de
# fonte confiável (webhook do cadastro, `PATCH /auth/me`). O que mudou é que
# ela deixou de BLOQUEAR o acesso.
#
# Se um dia voltar a fazer falta — RQE, rastro médico-legal, venda de insights —
# é acrescentar `PENDENCIA_CRM` de volta a `_ORDEM` e à função abaixo.
PENDENCIA_CRM = "crm"

# Ordem = ordem de apresentação na tela. Os apps renderizam a lista como vem,
# e é isto que faz o formulário compartilhado não precisar de lógica própria.
_ORDEM = (
    PENDENCIA_ACEITE,
    PENDENCIA_NOME,
    PENDENCIA_MED_STATUS,
    PENDENCIA_ESPECIALIDADE,
)


def pendencias(user, *, aceite_vigente: bool) -> list[str]:
    """O que ainda falta no perfil, calculado NO SERVIDOR.

    Esta função é a razão de o onboarding não precisar ser reimplementado em
    cada app. Os três frontends não decidem o que falta — eles renderizam esta
    lista. Uma exigência nova entra aqui e os três herdam de graça; se cada app
    decidisse, uma regra nova viraria três mudanças e três divergências, que é
    exatamente o mecanismo que produziu as três listas de especialidade que este
    trabalho veio consertar.

    `aceite_vigente` vem de fora (`consent_service.situacao_atual`) em vez de ser
    consultado aqui: mantém a função pura, síncrona e testável sem banco.
    """
    faltando: set[str] = set()

    if not aceite_vigente:
        faltando.add(PENDENCIA_ACEITE)
    if not (getattr(user, "name", None) or "").strip():
        faltando.add(PENDENCIA_NOME)

    med_status = getattr(user, "med_status", None)

    # Sem estágio de carreira não dá para saber o que mais exigir: graduando não
    # tem CRM, generalista não tem especialidade. Pedir esta resposta primeiro
    # (e só ela) evita cobrar de alguém um documento que ele legitimamente não
    # possui. É a única fonte automática que não existe — nem a WAID nem o grupo
    # `[CFM]` distinguem residente de especialista.
    if med_status is None:
        faltando.add(PENDENCIA_MED_STATUS)
        return [p for p in _ORDEM if p in faltando]

    # Graduando não tem especialidade — e isso não é pendência, é o estado
    # correto dele.
    if med_status == "graduando":
        return [p for p in _ORDEM if p in faltando]

    # Especialidade só é exigida de quem declarou tê-la. Generalista sem
    # especialidade é um perfil completo, não um cadastro pela metade.
    if med_status in ("residente", "especialista") and not getattr(user, "specialty_slug", None):
        faltando.add(PENDENCIA_ESPECIALIDADE)

    return [p for p in _ORDEM if p in faltando]


def perfil_completo(user, *, aceite_vigente: bool) -> bool:
    return not pendencias(user, aceite_vigente=aceite_vigente)
