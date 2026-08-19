"""Baseline do schema completo.

Ponto de partida unico da cadeia de migrations.

POR QUE ELA EXISTE
------------------
Ate 2026-08-19 o banco NAO podia ser reconstruido do zero: o schema original
nasceu de um `Base.metadata.create_all()` fora do Alembic, e as 21 migrations
seguintes eram apenas ALTERs em cima de tabelas que nenhuma migration criava.
`alembic upgrade head` num banco vazio falhava em "relation users does not exist".

Esta migration captura o schema inteiro no estado em que ele estava, e as
migrations historicas foram arquivadas em `alembic/versions_legacy/` (mantidas
no repositorio como registro, fora do caminho lido pelo Alembic).

Bancos que ja existiam foram marcados com `alembic stamp 000_baseline`, sem
re-executar nada.

Revision ID: 000_baseline
Revises: 
Create Date: 2026-08-19 10:59:46.877123
"""
from collections.abc import Sequence

import pgvector.sqlalchemy  # a coluna de embedding usa o tipo VECTOR
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision: str = '000_baseline'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Pre-requisitos que o autogenerate nao detecta: a extensao pgvector (usada
    # pela coluna de embedding do cache semantico) e o schema `calculators`.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS calculators")

    op.create_table('specialties',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug'),
    schema='calculators'
    )
    op.create_table('company',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('slug', sa.String(length=255), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('company_status', sa.Boolean(), nullable=False),
    sa.Column('legacy_company_id', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('model_pricing',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('model_id', sa.String(length=100), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('provider_type', sa.String(length=50), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('input_per_million', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('output_per_million', sa.Numeric(precision=10, scale=4), nullable=False),
    sa.Column('status', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('model_id')
    )
    op.create_table('otp_codes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('code', sa.String(length=6), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.Column('failed_attempts', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_otp_codes_email'), 'otp_codes', ['email'], unique=False)
    op.create_table('semantic_cache',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('mode', sa.String(length=50), nullable=False),
    sa.Column('normalized_prompt', sa.Text(), nullable=False),
    sa.Column('prompt_embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=False),
    sa.Column('response_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('hit_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_semantic_cache_expires_at'), 'semantic_cache', ['expires_at'], unique=False)
    op.create_table('calculator_definitions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('specialty_id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=150), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('engine_type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['specialty_id'], ['calculators.specialties.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug'),
    schema='calculators'
    )
    op.create_index('ix_calculator_definitions_specialty_status', 'calculator_definitions', ['specialty_id', 'status'], unique=False, schema='calculators')
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('phone_number', sa.String(length=20), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('crm', sa.String(length=20), nullable=True),
    sa.Column('crm_state', sa.String(length=2), nullable=True),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('med_status', sa.String(length=50), nullable=True),
    sa.Column('specialty', sa.String(length=100), nullable=True),
    sa.Column('enrollment_date', sa.Date(), nullable=True),
    sa.Column('onboarding_complete', sa.Boolean(), nullable=False),
    sa.Column('status', sa.Boolean(), nullable=False),
    sa.Column('legacy_user_id', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('calculator_favorites',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('calculator_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['calculator_id'], ['calculators.calculator_definitions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'calculator_id', name='uq_calculator_favorites_user_calculator'),
    schema='calculators'
    )
    op.create_index('ix_calculator_favorites_user', 'calculator_favorites', ['user_id'], unique=False, schema='calculators')
    op.create_table('calculator_fields',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('calculator_id', sa.UUID(), nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('field_type', sa.String(length=30), nullable=False),
    sa.Column('unit', sa.String(length=30), nullable=True),
    sa.Column('required', sa.Boolean(), nullable=False),
    sa.Column('min_value', sa.Float(), nullable=True),
    sa.Column('max_value', sa.Float(), nullable=True),
    sa.Column('max_length', sa.Integer(), nullable=True),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['calculator_id'], ['calculators.calculator_definitions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('calculator_id', 'key', name='uq_calculator_fields_calculator_key'),
    schema='calculators'
    )
    op.create_table('calculator_versions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('calculator_id', sa.UUID(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('formula_key', sa.String(length=150), nullable=False),
    sa.Column('interpretation_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('clinical_reference', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['calculator_id'], ['calculators.calculator_definitions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('calculator_id', 'version_number', name='uq_calculator_versions_calculator_version'),
    schema='calculators'
    )
    op.create_index('uq_calculator_versions_one_active', 'calculator_versions', ['calculator_id'], unique=True, schema='calculators', postgresql_where=sa.text('is_active'))
    op.create_table('consent_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('consent_type', sa.String(length=100), nullable=False),
    sa.Column('accepted', sa.Boolean(), nullable=False),
    sa.Column('ip_address', postgresql.INET(), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('file_extractions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('file_type', sa.String(length=50), nullable=False),
    sa.Column('extracted_text', sa.Text(), nullable=False),
    sa.Column('image_base64', sa.Text(), nullable=True),
    sa.Column('image_media_type', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_file_extractions_user_id', 'file_extractions', ['user_id'], unique=False)
    op.create_table('folders',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_folders_user_created_at', 'folders', ['user_id', 'created_at'], unique=False)
    op.create_table('invite_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('token', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.create_table('user_preferences',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('selected_models', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('ui_settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('notification_prefs', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('user_weekly_usage',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('week_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('total_cost_usd', sa.Numeric(precision=10, scale=6), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('conversations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('folder_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=True),
    sa.Column('feature', sa.String(length=50), nullable=False),
    sa.Column('status', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversations_user_status_updated_at', 'conversations', ['user_id', 'status', 'updated_at'], unique=False)
    op.create_table('interactions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('feature', sa.String(length=50), nullable=False),
    sa.Column('mode', sa.String(length=50), nullable=True),
    sa.Column('input_type', sa.String(length=20), nullable=False),
    sa.Column('prompt_text', sa.Text(), nullable=False),
    sa.Column('prompt_sanitized', sa.Boolean(), nullable=False),
    sa.Column('triage_confidence', sa.Float(), nullable=True),
    sa.Column('triage_category', sa.String(length=50), nullable=True),
    sa.Column('response_time_ms', sa.Integer(), nullable=True),
    sa.Column('cache_hit', sa.Boolean(), nullable=False),
    sa.Column('token_cost_usd', sa.Numeric(precision=10, scale=6), nullable=False),
    sa.Column('confidence_score', sa.Float(), nullable=True),
    sa.Column('specialty_detected', sa.String(length=100), nullable=True),
    sa.Column('topic_detected', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('clarification_questions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_interactions_conversation_feature', 'interactions', ['conversation_id', 'feature'], unique=False)
    op.create_index('ix_interactions_conversation_user_status', 'interactions', ['conversation_id', 'user_id', 'status'], unique=False)
    op.create_index('ix_interactions_user_created_at', 'interactions', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_interactions_user_feature', 'interactions', ['user_id', 'feature'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('interaction_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('entity_type', sa.String(length=100), nullable=True),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('ip_address', postgresql.INET(), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['interaction_id'], ['interactions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('calculator_executions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('calculator_id', sa.UUID(), nullable=False),
    sa.Column('version_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('interaction_id', sa.UUID(), nullable=True),
    sa.Column('inputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('interpretation', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['calculator_id'], ['calculators.calculator_definitions.id'], ),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
    sa.ForeignKeyConstraint(['interaction_id'], ['interactions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['calculators.calculator_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='calculators'
    )
    op.create_index('ix_calculator_executions_calculator_user_created_at', 'calculator_executions', ['calculator_id', 'user_id', sa.text('created_at DESC')], unique=False, schema='calculators')
    op.create_table('interaction_medications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('interaction_id', sa.UUID(), nullable=False),
    sa.Column('medication_raw', sa.String(length=255), nullable=False),
    sa.Column('medication_normalized', sa.String(length=255), nullable=True),
    sa.Column('atc_code', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['interaction_id'], ['interactions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interaction_medications_interaction_id'), 'interaction_medications', ['interaction_id'], unique=False)
    op.create_table('interaction_responses',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('interaction_id', sa.UUID(), nullable=False),
    sa.Column('model_used', sa.String(length=100), nullable=False),
    sa.Column('response_text', sa.Text(), nullable=False),
    sa.Column('response_time_ms', sa.Integer(), nullable=True),
    sa.Column('tokens_in', sa.Integer(), nullable=True),
    sa.Column('tokens_out', sa.Integer(), nullable=True),
    sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=False),
    sa.Column('is_fallback', sa.Boolean(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['interaction_id'], ['interactions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interaction_responses_interaction_id'), 'interaction_responses', ['interaction_id'], unique=False)
    op.create_table('pharma_alerts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('interaction_id', sa.UUID(), nullable=False),
    sa.Column('alert_level', sa.Integer(), nullable=False),
    sa.Column('alert_color', sa.String(length=20), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('source_api', sa.String(length=50), nullable=False),
    sa.Column('doctor_justification', sa.Text(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['interaction_id'], ['interactions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pharma_alerts_interaction_id'), 'pharma_alerts', ['interaction_id'], unique=False)
    op.create_table('pubmed_validations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('interaction_id', sa.UUID(), nullable=False),
    sa.Column('pmid', sa.String(length=20), nullable=False),
    sa.Column('article_title', sa.Text(), nullable=True),
    sa.Column('abstract_snippet', sa.Text(), nullable=True),
    sa.Column('relevance_score', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['interaction_id'], ['interactions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pubmed_validations_interaction_id'), 'pubmed_validations', ['interaction_id'], unique=False)
    # ### end Alembic commands ###


    # Indice ivfflat para busca por similaridade de cosseno no cache semantico.
    # O autogenerate nao reproduz indices de metodo especifico do pgvector.
    op.execute(
        "CREATE INDEX IF NOT EXISTS semantic_cache_embedding_idx ON semantic_cache "
        "USING ivfflat (prompt_embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS semantic_cache_mode_expires_idx "
        "ON semantic_cache (mode, expires_at)"
    )


def downgrade() -> None:
    """Derrubar a baseline apaga o banco inteiro. Existe por completude do
    contrato do Alembic; nao e para ser usada em producao."""
    op.drop_index(op.f('ix_pubmed_validations_interaction_id'), table_name='pubmed_validations')
    op.drop_table('pubmed_validations')
    op.drop_index(op.f('ix_pharma_alerts_interaction_id'), table_name='pharma_alerts')
    op.drop_table('pharma_alerts')
    op.drop_index(op.f('ix_interaction_responses_interaction_id'), table_name='interaction_responses')
    op.drop_table('interaction_responses')
    op.drop_index(op.f('ix_interaction_medications_interaction_id'), table_name='interaction_medications')
    op.drop_table('interaction_medications')
    op.drop_index('ix_calculator_executions_calculator_user_created_at', table_name='calculator_executions', schema='calculators')
    op.drop_table('calculator_executions', schema='calculators')
    op.drop_table('audit_logs')
    op.drop_index('ix_interactions_user_feature', table_name='interactions')
    op.drop_index('ix_interactions_user_created_at', table_name='interactions')
    op.drop_index('ix_interactions_conversation_user_status', table_name='interactions')
    op.drop_index('ix_interactions_conversation_feature', table_name='interactions')
    op.drop_table('interactions')
    op.drop_index('ix_conversations_user_status_updated_at', table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('user_weekly_usage')
    op.drop_table('user_preferences')
    op.drop_table('invite_tokens')
    op.drop_index('ix_folders_user_created_at', table_name='folders')
    op.drop_table('folders')
    op.drop_index('ix_file_extractions_user_id', table_name='file_extractions')
    op.drop_table('file_extractions')
    op.drop_table('consent_logs')
    op.drop_index('uq_calculator_versions_one_active', table_name='calculator_versions', schema='calculators', postgresql_where=sa.text('is_active'))
    op.drop_table('calculator_versions', schema='calculators')
    op.drop_table('calculator_fields', schema='calculators')
    op.drop_index('ix_calculator_favorites_user', table_name='calculator_favorites', schema='calculators')
    op.drop_table('calculator_favorites', schema='calculators')
    op.drop_table('users')
    op.drop_index('ix_calculator_definitions_specialty_status', table_name='calculator_definitions', schema='calculators')
    op.drop_table('calculator_definitions', schema='calculators')
    op.drop_index(op.f('ix_semantic_cache_expires_at'), table_name='semantic_cache')
    op.drop_table('semantic_cache')
    op.drop_index(op.f('ix_otp_codes_email'), table_name='otp_codes')
    op.drop_table('otp_codes')
    op.drop_table('model_pricing')
    op.drop_table('company')
    op.drop_table('specialties', schema='calculators')
    # ### end Alembic commands ###
