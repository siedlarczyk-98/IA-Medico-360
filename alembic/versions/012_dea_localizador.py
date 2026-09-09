"""Cria o schema dea: locais, dispositivos e verificacoes.

Localizador colaborativo de DEA (desfibrilador externo automatico). Unico modulo
publico do produto: sem FK para `users`, autoria por hash rotativo de IP.

Nenhuma extensao do Postgres e criada. A busca por raio usa bounding box sobre
o indice btree `(latitude, longitude)` mais Haversine em SQL — decisao tomada
porque `tests/conftest.py` monta o schema por `Base.metadata.create_all`, entao
indice de expressao ou extensao criados aqui NAO existiriam no banco de teste, e
o teste da busca deixaria de exercitar o caminho de producao. Com alguns
milhares de registros o ganho de PostGIS/earthdistance nao paga essa divergencia.

Revision ID: 012_dea
Revises: 011_indices_auditoria
Create Date: 2026-09-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision: str = "012_dea"
down_revision: str | None = "011_indices_auditoria"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "dea"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "locais",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("endereco", sa.String(240)),
        sa.Column("cidade", sa.String(120)),
        sa.Column("uf", sa.String(2)),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        # Materializadas para o indice de deduplicacao (~11m de resolucao).
        sa.Column("lat_arredondada", sa.Float, nullable=False),
        sa.Column("lon_arredondada", sa.Float, nullable=False),
        # Texto livre, exibido e nunca interpretado. Ver o docstring do modelo
        # para por que a versao estruturada foi descartada.
        sa.Column("horario_texto", sa.String(200)),
        sa.Column("acesso_24h", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    # Pre-filtro da busca por raio.
    op.create_index("ix_dea_locais_lat_lon", "locais", ["latitude", "longitude"], schema=SCHEMA)
    # Deteccao de duplicata. Nao e UNIQUE de proposito: dois predios vizinhos
    # podem cair na mesma celula, e recusar o cadastro seria pior que ter o que
    # fundir depois.
    op.create_index(
        "ix_dea_locais_dedupe",
        "locais",
        ["lat_arredondada", "lon_arredondada"],
        schema=SCHEMA,
    )

    op.create_table(
        "dispositivos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "local_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.locais.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("descricao_localizacao", sa.Text),
        # VARCHAR e nao ENUM nativo: ver docs/ARQUITETURA_TECNICA.md 11.1. Vamos
        # acrescentar status neste modulo, e `ALTER TYPE` e caro.
        sa.Column("acesso", sa.String(30), nullable=False, server_default="publico_livre"),
        sa.Column("foto_url", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
        sa.Column("origem", sa.String(20), nullable=False, server_default="colaborativo"),
        # Cache denormalizado de `verificacoes`, para a listagem nao fazer
        # subconsulta correlacionada dentro da busca por raio.
        sa.Column("verificacoes_positivas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("verificacoes_negativas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ultima_verificacao_em", sa.DateTime(timezone=True)),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        # Hash rotativo, nunca o IP em claro (modulo publico e anonimo).
        sa.Column("criado_por_ip_hash", sa.String(64)),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dea_dispositivos_local_status",
        "dispositivos",
        ["local_id", "status"],
        schema=SCHEMA,
    )

    op.create_table(
        "verificacoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dispositivo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.dispositivos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("observacao", sa.Text),
        sa.Column("verificado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_hash", sa.String(64)),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dea_verificacoes_dispositivo",
        "verificacoes",
        ["dispositivo_id", "verificado_em"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
