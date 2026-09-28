"""Schema `gerencial`: views para o dashboard da diretoria no Metabase.

O Metabase NAO le as tabelas do app. O banco guarda texto clinico (pergunta,
resposta, anexo extraido, embeddings) e dados pessoais (e-mail, telefone, CRM, IP);
um usuario de BI com SELECT nelas deixaria qualquer diretor abrir uma conversa —
e, com o MCP do Metabase, mandaria o resultado para um LLM. Por isso:

- tudo que o dashboard enxerga vive neste schema, como VIEW;
- nenhuma view expoe texto livre, e-mail, nome, telefone, CRM, IP ou user-agent;
- quem e quem vira `usuario_ref`, um pseudonimo estavel (hash do id) — permite
  contar usuarios distintos e montar coortes sem identificar ninguem;
- o role `gerencial_leitura` (NOLOGIN) so tem SELECT aqui. A view roda com os
  direitos do dono, entao o role nao precisa — e nao tem — acesso as tabelas.

O login do Metabase e criado A MAO em producao, fora da migration, para a senha
nao ir para o repositorio (roteiro em docs/dashboard-gerencial.md):

    CREATE ROLE metabase LOGIN PASSWORD '...' IN ROLE gerencial_leitura;

Contas `admin` ficam fora de todas as views: sao a equipe testando, e inflariam
adocao e custo. Contas de teste com perfil `beta_user` continuam contando.

`dia` e sempre a data em America/Sao_Paulo; `criado_em` fica em UTC (timestamptz)
para quem quiser agrupar por hora no proprio Metabase.

Revision ID: 016_schema_gerencial
Revises: 015_otp_code_hmac
Create Date: 2026-09-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "016_schema_gerencial"
down_revision: str | None = "015_otp_code_hmac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "gerencial_leitura"

# Pseudonimo do usuario. 16 hex bastam para nao colidir na escala do produto e
# deixam a coluna legivel numa tabela do Metabase.
_REF_USUARIO = "left(md5({col}::text), 16)"
_DIA = "({col} AT TIME ZONE 'America/Sao_Paulo')::date"
_NAO_ADMIN = "COALESCE(u.role, '') <> 'admin'"

VIEWS: dict[str, str] = {
    "usuarios": f"""
        SELECT
            {_REF_USUARIO.format(col="u.id")}           AS usuario_ref,
            u.created_at                                 AS cadastrado_em,
            {_DIA.format(col="u.created_at")}            AS dia_cadastro,
            u.specialty                                  AS especialidade,
            u.profissao                                  AS profissao,
            u.med_status                                 AS estagio_carreira,
            u.crm_state                                  AS uf,
            CASE WHEN u.waid_uuid IS NOT NULL THEN 'waid' ELSE 'direto' END AS origem,
            u.onboarding_complete                        AS onboarding_completo,
            u.status                                     AS ativo
        FROM users u
        WHERE {_NAO_ADMIN}
    """,
    # Uma linha por pergunta ao assistente (orquestrador e agregador). Sem o
    # texto da pergunta e sem `topic_detected`, que e resumo livre do assunto
    # clinico; `specialty_detected` e `triage_category` sao categorias fechadas.
    "perguntas": f"""
        SELECT
            left(md5(i.id::text), 16)                    AS pergunta_ref,
            {_REF_USUARIO.format(col="i.user_id")}       AS usuario_ref,
            left(md5(i.conversation_id::text), 16)       AS conversa_ref,
            i.created_at                                 AS criado_em,
            {_DIA.format(col="i.created_at")}            AS dia,
            i.feature                                    AS produto,
            i.mode                                       AS modo,
            i.input_type                                 AS tipo_entrada,
            i.status                                     AS status,
            i.triage_category                            AS categoria_triagem,
            i.specialty_detected                         AS especialidade_detectada,
            u.specialty                                  AS especialidade_usuario,
            i.response_time_ms                           AS tempo_resposta_ms,
            i.cache_hit                                  AS cache_hit,
            i.token_cost_usd                             AS custo_usd,
            (c.folder_id IS NOT NULL)                    AS em_pasta,
            EXISTS (SELECT 1 FROM file_extractions f WHERE f.interaction_id = i.id)
                                                         AS com_anexo,
            EXISTS (SELECT 1 FROM pharma_alerts p WHERE p.interaction_id = i.id)
                                                         AS com_alerta_farmaco
        FROM interactions i
        JOIN users u ON u.id = i.user_id
        LEFT JOIN conversations c ON c.id = i.conversation_id
        WHERE {_NAO_ADMIN}
    """,
    # Uma linha por chamada de modelo. O custo total de uma pergunta ja esta em
    # `perguntas.custo_usd`; esta view serve para quebrar por modelo/provedor —
    # nao somar as duas no mesmo grafico.
    "respostas_modelo": f"""
        SELECT
            left(md5(r.interaction_id::text), 16)        AS pergunta_ref,
            r.created_at                                 AS criado_em,
            {_DIA.format(col="r.created_at")}            AS dia,
            r.model_used                                 AS modelo,
            mp.display_name                              AS modelo_nome,
            mp.provider                                  AS provedor,
            r.tokens_in                                  AS tokens_entrada,
            r.tokens_out                                 AS tokens_saida,
            r.cost_usd                                   AS custo_usd,
            r.response_time_ms                           AS tempo_resposta_ms,
            r.is_fallback                                AS fallback,
            (r.error_message IS NOT NULL)                AS com_erro
        FROM interaction_responses r
        JOIN interactions i ON i.id = r.interaction_id
        JOIN users u ON u.id = i.user_id
        LEFT JOIN model_pricing mp ON mp.model_id = r.model_used
        WHERE {_NAO_ADMIN}
    """,
    # Entrada pela Waid (embed). O login por codigo de e-mail nao grava
    # auditoria, entao isto mede acesso pela Waid, nao todo acesso.
    "acessos": f"""
        SELECT
            {_REF_USUARIO.format(col="a.user_id")}       AS usuario_ref,
            a.created_at                                 AS criado_em,
            {_DIA.format(col="a.created_at")}            AS dia,
            a.metadata ->> 'via'                         AS via
        FROM audit_logs a
        JOIN users u ON u.id = a.user_id
        WHERE a.action = 'auth.embed' AND {_NAO_ADMIN}
    """,
    # Sem `inputs`, `result` e `interpretation`: sao dados do paciente.
    # A PREVENT roda sem estado e nao aparece aqui.
    "calculadoras": f"""
        SELECT
            {_REF_USUARIO.format(col="e.user_id")}       AS usuario_ref,
            e.created_at                                 AS criado_em,
            {_DIA.format(col="e.created_at")}            AS dia,
            d.name                                       AS calculadora,
            s.name                                       AS especialidade_calculadora,
            (e.interaction_id IS NOT NULL)               AS pelo_chat
        FROM calculators.calculator_executions e
        JOIN calculators.calculator_definitions d ON d.id = e.calculator_id
        JOIN calculators.specialties s ON s.id = d.specialty_id
        JOIN users u ON u.id = e.user_id
        WHERE {_NAO_ADMIN}
    """,
    "noticias_artigos": f"""
        SELECT
            a.id                                         AS artigo_id,
            a.journal_slug                               AS revista,
            COALESCE(a.rewritten_title, a.original_title) AS titulo,
            a.status                                     AS status,
            a.retry_count                                AS tentativas,
            a.created_at                                 AS coletado_em,
            {_DIA.format(col="a.created_at")}            AS dia_coleta,
            a.visible_at                                 AS publicado_em,
            {_DIA.format(col="a.visible_at")}            AS dia_publicacao
        FROM news.articles a
    """,
    "noticias_digest": f"""
        SELECT
            {_REF_USUARIO.format(col="d.user_id")}       AS usuario_ref,
            d.enviado_em                                 AS enviado_em,
            {_DIA.format(col="d.enviado_em")}            AS dia,
            COALESCE(jsonb_array_length(d.article_ids), 0) AS qtd_artigos
        FROM news.digest_sends d
        JOIN users u ON u.id = d.user_id
        WHERE {_NAO_ADMIN}
    """,
    "noticias_favoritos": f"""
        SELECT
            {_REF_USUARIO.format(col="f.user_id")}       AS usuario_ref,
            f.article_id                                 AS artigo_id,
            f.created_at                                 AS criado_em,
            {_DIA.format(col="f.created_at")}            AS dia
        FROM news.favorites f
        JOIN users u ON u.id = f.user_id
        WHERE {_NAO_ADMIN}
    """,
    # Sem `nome`, `endereco` e coordenadas: o painel e de cobertura por cidade,
    # nao um mapa — o mapa ja e o proprio produto.
    "dea_dispositivos": f"""
        SELECT
            left(md5(d.id::text), 16)                    AS dispositivo_ref,
            d.status                                     AS status,
            d.origem                                     AS origem,
            d.acesso                                     AS acesso,
            l.cidade                                     AS cidade,
            l.uf                                         AS uf,
            l.acesso_24h                                 AS acesso_24h,
            d.verificacoes_positivas                     AS verificacoes_positivas,
            d.verificacoes_negativas                     AS verificacoes_negativas,
            d.ultima_verificacao_em                      AS ultima_verificacao_em,
            d.criado_em                                  AS criado_em,
            {_DIA.format(col="d.criado_em")}             AS dia
        FROM dea.dispositivos d
        JOIN dea.locais l ON l.id = d.local_id
    """,
    # Sem nome, e-mail e telefone do lead.
    "captacao": f"""
        SELECT
            lp.name                                      AS landing_page,
            lp.slug                                      AS landing_slug,
            s.created_at                                 AS criado_em,
            {_DIA.format(col="s.created_at")}            AS dia,
            (s.user_id IS NOT NULL)                      AS virou_usuario,
            (s.lgpd_consent_at IS NOT NULL)              AS consentiu_lgpd,
            s.notify_on_availability                     AS quer_aviso
        FROM landing_pages.submissions s
        JOIN landing_pages.landing_pages lp ON lp.id = s.landing_page_id
    """,
}


def comandos_upgrade() -> list[str]:
    """Separado de `upgrade()` para o teste rodar o MESMO SQL no banco de teste,
    que e montado por `create_all` e nao passa pelas migrations."""
    return [
        "CREATE SCHEMA gerencial",
        *(f"CREATE VIEW gerencial.{nome} AS {corpo}" for nome, corpo in VIEWS.items()),
        # Role e objeto do cluster, nao do banco: sobrevive a um downgrade e ja
        # existe no segundo `upgrade` do CI. Dai o IF NOT EXISTS.
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN;
            END IF;
        END
        $$
        """,
        f"GRANT USAGE ON SCHEMA gerencial TO {ROLE}",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA gerencial TO {ROLE}",
        # View criada depois, por migration futura do mesmo dono, ja nasce legivel.
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA gerencial GRANT SELECT ON TABLES TO {ROLE}",
    ]


def upgrade() -> None:
    for sql in comandos_upgrade():
        op.execute(sql)


def downgrade() -> None:
    # O role fica: pode ter membros (o login do Metabase), e DROP ROLE falharia.
    # Sem o schema ele nao enxerga nada.
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA gerencial REVOKE SELECT ON TABLES FROM {ROLE}")
    op.execute("DROP SCHEMA gerencial CASCADE")
