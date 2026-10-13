"""Quem conta como usuário, por qual porta entrou, e a PREVENT como uso.

Regras do Ruben, fechadas em 2026-10-13 olhando o painel com os dados reais
(a leitura dos grupos está em app/medicina/canal.py):

1. SÓ CONTA quem está num grupo `[Cursos Active]`, `[CFM]` ou `[ONBOARDING]` da
   Waid — a cópia diária em `membros_waid`. Quem não está em nenhum deles não
   conta nunca, nem se tiver aberto a IA: na prática, equipe e contas antigas
   de login direto. A 018 contava toda conta do app; esta não.

2. CANAL, decidido pela sincronização e só exibido aqui:
     cursos_active -> 'Cursos Active'
     lp_medico360  -> 'LP do Médico 360'  ([CFM]/[ONBOARDING] sem andar de farmacêutica)
     immerso       -> 'Usuário Immerso'   ([CFM]/[ONBOARDING] com andar de farmacêutica)

3. CONTAS DE TESTE SEM CONTA NO APP. `role = 'test'` só pega quem tem conta.
   Os cadastros de teste que só existem na Waid (lucas.mendes+N, arthur+...,
   e-mail descartável) saem pelo domínio do e-mail: `_DOMINIOS_DE_TESTE`.

4. LIGAÇÃO MEMBRO -> CONTA pelo id da Waid ou, para a conta criada por login
   direto (sem id da Waid), pelo e-mail. Sem isso a mesma pessoa aparecia duas
   vezes: uma como membro sem conta, outra como conta sem grupo.

5. A PREVENT CONTA COMO USO. O endpoint grava em `audit_logs` só QUEM usou e
   QUANDO (`prevent.calculo`, nenhum dado do paciente); aqui isso entra em
   `calculadoras`, `usou_ia` e `ultimo_uso_em`. Vale do deploy em diante.

`usuarios`, `acesso`, `usuarios_lista` e `calculadoras` são recriadas por DROP +
CREATE (tipos de coluna mudam). As perguntas do Metabase são SQL e não
dependem do objeto; o GRANT é refeito.

ORDEM DE SUBIDA: o código que grava o canal novo (`lp_medico360`/`immerso`) e
lê o `[ONBOARDING]` precisa estar no ar, e ter rodado uma sincronização, ANTES
desta migration. Sem isso as views desta migration mostram o canal antigo.

Revision ID: 019_prevent_conta_como_uso
Revises: 018_canal_e_acesso
Create Date: 2026-10-13 00:00:00.000000
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers
revision: str = "019_prevent_conta_como_uso"
down_revision: str | None = "018_canal_e_acesso"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_spec = importlib.util.spec_from_file_location(
    "migration_018", Path(__file__).with_name("018_canal_e_acesso.py")
)
_m018 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m018)
_m017 = _m018._m017
_m016 = _m018._m016
_REF = _m016._REF_USUARIO
_DIA = _m016._DIA
ROLE = _m016.ROLE

# Igual a `prevent_router.ACAO_USO`. Repetido de propósito: migration não
# importa código da aplicação, que muda depois dela.
ACAO_PREVENT = "prevent.calculo"

# Domínios da equipe e dos e-mails descartáveis usados em teste (vistos na base
# em 2026-10-13). Quem tem e-mail num deles não conta, com ou sem conta no app.
_DOMINIOS_DE_TESTE = (
    "cursosactive.com.br", "paciente360.com.br", "immerso.com.br", "waid.io",
    "teste.com", "reumato.com",
    "slotbeer.com", "robustq.com", "dd2car.com", "uorak.com", "kingdais.com",
)
_DOMINIOS_SQL = ", ".join(f"'{d}'" for d in _DOMINIOS_DE_TESTE)


def _nao_e_teste(email: str) -> str:
    return f"COALESCE(lower(split_part({email}, '@', 2)), '') NOT IN ({_DOMINIOS_SQL})"


_CANAL = """CASE m.canal_entrada
            WHEN 'cursos_active' THEN 'Cursos Active'
            WHEN 'immerso'       THEN 'Usuário Immerso'
            ELSE 'LP do Médico 360'
        END"""


def _perfil(grupos: str, profissao: str) -> tuple[str, str]:
    """A regra da 018, com a fonte do grupo renomeada: agora vale para
    `[ONBOARDING]` também, não só para Cursos Active."""
    perfil, fonte = _m018._perfil(grupos, profissao)
    return perfil, fonte.replace("'cursos_active'", "'grupo_waid'")


_PROFISSAO = "COALESCE(m.profissao, u.profissao)"
_PERFIL, _PERFIL_FONTE = _perfil("COALESCE(m.grupos, '[]'::jsonb)", _PROFISSAO)

# A conta do app de um membro: pelo id da Waid; sem ele, pelo e-mail.
_LIGA_MEMBRO_A_CONTA = """(
            u.waid_uuid = m.waid_uuid
            OR (u.waid_uuid IS NULL AND lower(u.email) = lower(m.email))
        )"""

_FORA = f"""m.tem_acesso
        AND {_m017._FORA_DO_PAINEL}
        AND {_nao_e_teste("m.email")}
        AND {_nao_e_teste("u.email")}"""


# ── usuarios: uma linha por CONTA do app que conta ──────────────────────────

_USUARIOS = f"""
    SELECT
        {_REF.format(col="u.id")}                        AS usuario_ref,
        u.created_at                                     AS cadastrado_em,
        {_DIA.format(col="u.created_at")}                AS dia_cadastro,
        u.specialty                                      AS especialidade,
        {_PROFISSAO}                                     AS profissao,
        u.med_status                                     AS estagio_carreira,
        u.crm_state                                      AS uf,
        CASE WHEN u.waid_uuid IS NOT NULL THEN 'waid' ELSE 'direto' END AS origem,
        u.onboarding_complete                            AS onboarding_completo,
        u.status                                         AS ativo,
        {_PERFIL}                                        AS perfil,
        {_PERFIL_FONTE}                                  AS perfil_fonte,
        {_CANAL}                                         AS canal_entrada
    FROM users u
    JOIN LATERAL (
        SELECT * FROM membros_waid m
        WHERE m.tem_acesso AND {_LIGA_MEMBRO_A_CONTA}
        ORDER BY (m.waid_uuid = u.waid_uuid) DESC NULLS LAST
        LIMIT 1
    ) m ON true
    WHERE {_FORA}
"""

# ── acesso e usuarios_lista: uma linha por PESSOA com acesso ────────────────

_DE_PESSOAS = f"""
    FROM membros_waid m
    LEFT JOIN LATERAL (
        SELECT * FROM users u
        WHERE {_LIGA_MEMBRO_A_CONTA}
        ORDER BY (u.waid_uuid = m.waid_uuid) DESC NULLS LAST, u.created_at
        LIMIT 1
    ) u ON true
    LEFT JOIN LATERAL (
        SELECT count(*) AS qtd, max(i.created_at) AS ultima
        FROM interactions i WHERE i.user_id = u.id
    ) p ON true
    LEFT JOIN LATERAL (
        SELECT count(*) AS qtd, max(x.criado) AS ultima FROM (
            SELECT e.created_at AS criado
            FROM calculators.calculator_executions e WHERE e.user_id = u.id
            UNION ALL
            SELECT l.created_at
            FROM audit_logs l WHERE l.user_id = u.id AND l.action = '{ACAO_PREVENT}'
        ) x
    ) c ON true
    LEFT JOIN LATERAL (
        SELECT count(*) AS qtd, max(n.created_at) AS ultima
        FROM news.favorites n WHERE n.user_id = u.id
    ) f ON true
    LEFT JOIN LATERAL (
        SELECT max(l.created_at) AS ultima
        FROM audit_logs l WHERE l.user_id = u.id AND l.action = 'auth.embed'
    ) a ON true
    WHERE {_FORA}
"""

_USOU = "(COALESCE(p.qtd, 0) + COALESCE(c.qtd, 0) + COALESCE(f.qtd, 0)) > 0"

_COLUNAS_PESSOA = f"""
        left(md5(m.waid_uuid), 16)                       AS pessoa_ref,
        CASE WHEN u.id IS NOT NULL THEN {_REF.format(col="u.id")} END AS usuario_ref,
        {_CANAL}                                         AS canal_entrada,
        {_PROFISSAO}                                     AS profissao,
        {_PERFIL}                                        AS perfil,
        {_PERFIL_FONTE}                                  AS perfil_fonte,
        (u.id IS NOT NULL)                               AS abriu_ia,
        {_USOU}                                          AS usou_ia,
        LEAST(m.entrou_em, u.created_at)                 AS entrou_em,
        {_DIA.format(col="LEAST(m.entrou_em, u.created_at)")} AS dia_entrada,
        u.created_at                                     AS abriu_ia_em,
        GREATEST(p.ultima, c.ultima, f.ultima)           AS ultimo_uso_em"""

_ACESSO = f"SELECT {_COLUNAS_PESSOA} {_DE_PESSOAS}"

_LISTA = f"""
    SELECT {_COLUNAS_PESSOA},
        COALESCE(NULLIF(u.name, ''), m.nome)             AS nome,
        COALESCE(u.email, m.email)                       AS email,
        CASE
            WHEN {_USOU}          THEN 'Usou a IA'
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
        m.grupos                                         AS grupos_waid
    {_DE_PESSOAS}
"""

# ── calculadoras: as da 017 mais a PREVENT ──────────────────────────────────

_CALCULADORAS_017 = _m017.VIEWS["calculadoras"]
_CALCULADORAS = f"""{_CALCULADORAS_017}
    UNION ALL
    SELECT
        {_REF.format(col="l.user_id")},
        l.created_at,
        {_DIA.format(col="l.created_at")},
        'PREVENT',
        'Cardiologia',
        false
    FROM audit_logs l
    JOIN users u ON u.id = l.user_id
    WHERE l.action = '{ACAO_PREVENT}' AND {_m017._FORA_DO_PAINEL}
"""

VIEWS: dict[str, str] = {
    "usuarios": _USUARIOS,
    _m018.VIEW_ACESSO: _ACESSO,
    _m018.VIEW_LISTA: _LISTA,
    "calculadoras": _CALCULADORAS,
}
_VIEWS_018 = {
    "usuarios": _m018._USUARIOS,
    _m018.VIEW_ACESSO: _m018.VIEWS[_m018.VIEW_ACESSO],
    _m018.VIEW_LISTA: _m018.VIEWS[_m018.VIEW_LISTA],
    "calculadoras": _CALCULADORAS_017,
}


def _recriar(views: dict[str, str]) -> list[str]:
    return [
        *(f"DROP VIEW IF EXISTS gerencial.{nome}" for nome in views),
        *(f"CREATE VIEW gerencial.{nome} AS {corpo}" for nome, corpo in views.items()),
        *(f"GRANT SELECT ON gerencial.{nome} TO {ROLE}" for nome in views),
    ]


def comandos_upgrade() -> list[str]:
    """Separado de `upgrade()` para o teste rodar o MESMO SQL no banco de teste."""
    return _recriar(VIEWS)


def comandos_downgrade() -> list[str]:
    return _recriar(_VIEWS_018)


def upgrade() -> None:
    for sql in comandos_upgrade():
        op.execute(sql)


def downgrade() -> None:
    for sql in comandos_downgrade():
        op.execute(sql)
