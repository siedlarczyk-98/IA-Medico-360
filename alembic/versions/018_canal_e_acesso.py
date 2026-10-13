"""Canal de entrada, membros da Waid e o painel de acesso x uso.

Pedidos da diretoria (Ruben, 2026-10-13), todos sobre a mesma pergunta — quem
sao os usuarios do Medico 360 e o que cada um fez:

1. DE ONDE VEIO. Duas portas dao acesso: a pagina de cadastro (consulta o CRM e
   cria o grupo `[CFM] ...`) e a integracao do site dos cursos presenciais da
   Cursos Active (cria o membro com `[Cursos Active] <perfil> - <curso>`, sem
   passar pelo CFM). `users` ganha `waid_grupos` e `canal_entrada`, gravados no
   login (app/medicina/canal.py).

2. QUEM TEM ACESSO E NUNCA ABRIU O APP. `users` so tem quem abriu o app de IA.
   A tabela `membros_waid` e a copia diaria dos membros dos grupos `[CFM]` e
   `[Cursos Active]` (app/services/membros_waid_service.py) — e so deles: forca
   de vendas e areas de laboratorio nao contam (decisao do Ruben).

3. TRES NIVEIS, em `gerencial.acesso` (uma linha por pessoa):
   com acesso (membro desses grupos OU tem conta) > abriu a IA (tem conta) >
   usou a IA (pergunta, calculadora ou noticia favoritada).

4. PERFIL (especialista / residente / generalista / estudante / enfermagem),
   juntando o que o CFM diz, o que o grupo da Cursos Active diz e o que o
   medico declarou no onboarding. A regra esta em `_PERFIL`, abaixo.

5. A LISTA NOMINAL (`gerencial.usuarios_lista`): a UNICA view com nome e
   e-mail. Nada clinico, nem telefone, nem CRM. O destino esta no inventario de
   tratamento de dados — com o MCP do Metabase, a consulta passa por um LLM.

Contas `admin` e `test` continuam fora de tudo (017).

Revision ID: 018_canal_e_acesso
Revises: 017_gerencial_sem_contas_teste
Create Date: 2026-10-13 00:00:00.000000
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision: str = "018_canal_e_acesso"
down_revision: str | None = "017_gerencial_sem_contas_teste"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_spec = importlib.util.spec_from_file_location(
    "migration_017", Path(__file__).with_name("017_gerencial_sem_contas_teste.py")
)
_m017 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m017)
_m016 = _m017._m016

VIEW_ACESSO = "acesso"
VIEW_LISTA = "usuarios_lista"

# Fontes que so existem porque alguem consultou o CFM (identidade._FONTES_COM_CRM).
_VERIFICADO = "u.specialty_source IN ('waid_grupo', 'cfm', 'cadastro')"


def _tem_grupo(grupos: str, condicao: str) -> str:
    return f"EXISTS (SELECT 1 FROM jsonb_array_elements_text({grupos}) AS g(nome) WHERE {condicao})"


def _perfil(grupos: str, profissao: str) -> tuple[str, str]:
    """(perfil, perfil_fonte) em SQL. `u` pode ser nulo (membro sem conta).

    A ordem, e por que:
      1. enfermagem (grupo da Cursos Active)  -> nao e medico; sai da conta de medicos
      2. declarou residente                    -> o CFM nao separa R1 de especialista
      3. CFM com especialidade                 -> Especialista
      4. CFM sem especialidade (GENERALISTA)   -> Generalista
      5. grupo "Estudante ... Medicina"        -> Estudante
      6. o que declarou no onboarding
      7. grupo "Medico(a)" da Cursos Active    -> e medico, sem saber o estagio
      8. grupo "Profissionais de saude" (BLS)  -> outro profissional
    O que e verificado (CFM) vem antes do declarado; o grupo da Cursos Active e
    o perfil informado na compra — vale como fonte, mas so preenche o que o CFM
    e o onboarding nao responderam, exceto enfermagem e estudante, que o
    onboarding nao distingue (ele nao tem opcao de enfermagem).
    """
    cfm_esp = _tem_grupo(grupos, "g.nome ILIKE '[CFM]%' AND g.nome NOT ILIKE '[CFM]%GENERALISTA%'")
    cfm_gen = _tem_grupo(grupos, "g.nome ILIKE '[CFM]%GENERALISTA%'")
    perfil = f"""CASE
            WHEN {profissao} IN ('enfermeiro', 'estudante_enfermagem')        THEN 'Enfermagem'
            WHEN u.med_status = 'residente'                                    THEN 'Residente'
            WHEN (u.specialty_slug IS NOT NULL AND {_VERIFICADO}) OR {cfm_esp} THEN 'Especialista'
            WHEN u.crm_verified_at IS NOT NULL OR {cfm_gen}                    THEN 'Generalista'
            WHEN {profissao} = 'estudante_medicina'                            THEN 'Estudante'
            WHEN u.med_status = 'especialista'                                 THEN 'Especialista'
            WHEN u.med_status = 'generalista'                                  THEN 'Generalista'
            WHEN u.med_status = 'graduando'                                    THEN 'Estudante'
            WHEN {profissao} = 'medico'                                        THEN 'Médico, estágio não informado'
            WHEN {profissao} = 'profissional_saude'                            THEN 'Outro profissional de saúde'
            ELSE 'Não informado'
        END"""
    fonte = f"""CASE
            WHEN {profissao} IN ('enfermeiro', 'estudante_enfermagem')        THEN 'cursos_active'
            WHEN u.med_status = 'residente'                                    THEN 'declarado'
            WHEN (u.specialty_slug IS NOT NULL AND {_VERIFICADO}) OR {cfm_esp}
                 OR u.crm_verified_at IS NOT NULL OR {cfm_gen}                 THEN 'cfm'
            WHEN {profissao} = 'estudante_medicina'                            THEN 'cursos_active'
            WHEN u.med_status IS NOT NULL                                      THEN 'declarado'
            WHEN {profissao} IS NOT NULL                                       THEN 'cursos_active'
        END"""
    return perfil, fonte


def _canal(canal_col: str) -> str:
    return f"""CASE {canal_col}
            WHEN 'cursos_active' THEN 'Cursos Active'
            WHEN 'cadastro_cfm'  THEN 'Cadastro CFM'
            ELSE CASE
                WHEN u.id IS NULL           THEN 'Não identificado'
                WHEN u.waid_uuid IS NOT NULL THEN 'Waid, outros grupos'
                ELSE 'Login direto'
            END
        END"""


# ── gerencial.usuarios: a da 017 com perfil e canal no fim ──────────────────
# CREATE OR REPLACE so aceita coluna nova no FIM; as perguntas salvas continuam.
# `profissao` ja estava nela desde a 016 (vazia ate agora: so o login a grava).

_G_USUARIO = "COALESCE(u.waid_grupos, '[]'::jsonb)"
_PERFIL_U, _FONTE_U = _perfil(_G_USUARIO, "u.profissao")
_USUARIOS_017 = _m017.VIEWS["usuarios"]
_USUARIOS = _USUARIOS_017.replace(
    "        FROM users u",
    f"""        , {_PERFIL_U} AS perfil,
        {_FONTE_U} AS perfil_fonte,
        {_canal("u.canal_entrada")} AS canal_entrada
        FROM users u""",
    1,
)

# ── Uma linha por pessoa com acesso ─────────────────────────────────────────
# Pessoa = membro com acesso em `membros_waid` OU dono de conta em `users`.
# O UNION junta as duas pontas pelo `waid_uuid` sem duplicar quem esta nas duas.

_G_PESSOA = "COALESCE(m.grupos, u.waid_grupos, '[]'::jsonb)"
_PROF_PESSOA = "COALESCE(u.profissao, m.profissao)"
_PERFIL_P, _FONTE_P = _perfil(_G_PESSOA, _PROF_PESSOA)

_DE_PESSOAS = f"""
    FROM (
        SELECT m.waid_uuid, u.id AS user_id
        FROM membros_waid m LEFT JOIN users u ON u.waid_uuid = m.waid_uuid
        WHERE m.tem_acesso
        UNION
        SELECT u.waid_uuid, u.id FROM users u
    ) pessoa
    LEFT JOIN users u ON u.id = pessoa.user_id
    LEFT JOIN membros_waid m ON m.waid_uuid = pessoa.waid_uuid
    LEFT JOIN LATERAL (
        SELECT count(*) AS qtd, max(i.created_at) AS ultima
        FROM interactions i WHERE i.user_id = u.id
    ) p ON true
    LEFT JOIN LATERAL (
        SELECT count(*) AS qtd, max(e.created_at) AS ultima
        FROM calculators.calculator_executions e WHERE e.user_id = u.id
    ) c ON true
    LEFT JOIN LATERAL (
        SELECT count(*) AS qtd, max(n.created_at) AS ultima
        FROM news.favorites n WHERE n.user_id = u.id
    ) f ON true
    LEFT JOIN LATERAL (
        SELECT max(l.created_at) AS ultima
        FROM audit_logs l WHERE l.user_id = u.id AND l.action = 'auth.embed'
    ) a ON true
    WHERE {_m017._FORA_DO_PAINEL}
"""

# Mesma definicao de "usou" dos cards do painel: pergunta, calculadora ou
# noticia favoritada. A PREVENT e o mapa de DEA nao gravam uso por pessoa.
_USOU = "(COALESCE(p.qtd, 0) + COALESCE(c.qtd, 0) + COALESCE(f.qtd, 0)) > 0"

_COLUNAS_PESSOA = f"""
        left(md5(COALESCE(u.id::text, pessoa.waid_uuid)), 16) AS pessoa_ref,
        CASE WHEN u.id IS NOT NULL THEN {_m016._REF_USUARIO.format(col="u.id")} END AS usuario_ref,
        {_canal("COALESCE(u.canal_entrada, m.canal_entrada)")} AS canal_entrada,
        {_PROF_PESSOA}                                   AS profissao,
        {_PERFIL_P}                                      AS perfil,
        {_FONTE_P}                                       AS perfil_fonte,
        (m.waid_uuid IS NOT NULL AND m.tem_acesso)       AS em_grupo_medico360,
        (u.id IS NOT NULL)                               AS abriu_ia,
        {_USOU}                                          AS usou_ia,
        LEAST(m.entrou_em, u.created_at)                 AS entrou_em,
        {_m016._DIA.format(col="LEAST(m.entrou_em, u.created_at)")} AS dia_entrada,
        u.created_at                                     AS abriu_ia_em,
        GREATEST(p.ultima, c.ultima, f.ultima)           AS ultimo_uso_em"""

_ACESSO = f"SELECT {_COLUNAS_PESSOA} {_DE_PESSOAS}"

# A lista: as mesmas pessoas, com nome e e-mail e o detalhe do uso.
_LISTA = f"""
    SELECT {_COLUNAS_PESSOA},
        COALESCE(NULLIF(u.name, ''), m.nome)             AS nome,
        COALESCE(u.email, m.email)                       AS email,
        CASE
            WHEN {_USOU}       THEN 'Usou a IA'
            WHEN u.id IS NOT NULL THEN 'Abriu a IA, não usou'
            ELSE 'Só tem acesso'
        END                                              AS situacao,
        u.specialty                                      AS especialidade,
        u.crm_state                                      AS uf,
        u.onboarding_complete                            AS onboarding_completo,
        a.ultima                                         AS ultimo_acesso_waid_em,
        COALESCE(p.qtd, 0)                               AS perguntas,
        COALESCE(c.qtd, 0)                               AS calculadoras,
        COALESCE(f.qtd, 0)                               AS noticias_favoritadas,
        COALESCE(m.grupos, u.waid_grupos)                AS grupos_waid
    {_DE_PESSOAS}
"""

VIEWS: dict[str, str] = {VIEW_ACESSO: _ACESSO, VIEW_LISTA: _LISTA}


def comandos_upgrade() -> list[str]:
    """So as views. Separado para o teste, que monta tabela e coluna por `create_all`."""
    # O ALTER DEFAULT PRIVILEGES da 016 so vale para views do mesmo dono; o
    # GRANT explicito nao depende de quem roda a migration.
    return [
        f"CREATE OR REPLACE VIEW gerencial.usuarios AS {_USUARIOS}",
        *(f"CREATE VIEW gerencial.{nome} AS {corpo}" for nome, corpo in VIEWS.items()),
        *(f"GRANT SELECT ON gerencial.{nome} TO {_m016.ROLE}" for nome in VIEWS),
    ]


def comandos_downgrade() -> list[str]:
    # CREATE OR REPLACE nao remove coluna: a `usuarios` volta por DROP + CREATE.
    return [
        *(f"DROP VIEW gerencial.{nome}" for nome in VIEWS),
        "DROP VIEW gerencial.usuarios",
        f"CREATE VIEW gerencial.usuarios AS {_USUARIOS_017}",
        f"GRANT SELECT ON gerencial.usuarios TO {_m016.ROLE}",
    ]


def upgrade() -> None:
    op.add_column("users", sa.Column("waid_grupos", postgresql.JSONB(), nullable=True))
    op.add_column("users", sa.Column("canal_entrada", sa.String(30), nullable=True))
    op.create_table(
        "membros_waid",
        sa.Column("waid_uuid", sa.String(64), primary_key=True),
        sa.Column("waid_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("nome", sa.String(255), nullable=True),
        sa.Column("grupos", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("canal_entrada", sa.String(30), nullable=True),
        sa.Column("profissao", sa.String(40), nullable=True),
        sa.Column("entrou_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tem_acesso", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    for sql in comandos_upgrade():
        op.execute(sql)


def downgrade() -> None:
    for sql in comandos_downgrade():
        op.execute(sql)
    op.drop_table("membros_waid")
    op.drop_column("users", "canal_entrada")
    op.drop_column("users", "waid_grupos")
