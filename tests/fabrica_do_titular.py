"""
"Usuário completo": uma linha em TODA tabela ligada a `users`.

POR QUE GENÉRICO
O teste antigo da exclusão de conta criava preferência e auditoria, à mão, e
passava — enquanto a exclusão falhava em produção para toda conta real, por
causa de quatro tabelas que ninguém lembrou de pôr no cenário. Um construtor
escrito à mão repete o defeito que veio consertar: tabela nova, cenário velho.

Este lê o `metadata`. Tabela nova ligada a usuário entra no cenário sozinha, e
se a exclusão ou a exportação não souberem lidar com ela, o teste quebra no
mesmo PR que criou a tabela.

Valores são gerados pelo tipo da coluna. Não precisam fazer sentido clínico:
o que se testa é o destino das LINHAS, não o conteúdo.
"""

import uuid
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy import insert
from sqlalchemy.dialects import postgresql

from app.core.database import Base

USERS = "users"

# Colunas que não podem ficar com o valor automático. Dois motivos possíveis: o
# valor gerado pelo tipo violaria uma regra do schema (CHECK, enum em texto), ou
# o padrão da coluna é vazio e a exportação não teria o que mostrar.
VALORES_FIXOS: dict[tuple[str, str], object] = {
    # O padrão é `{}`: sem isto a seção "preferencias" sai vazia e o teste de
    # exportação não distingue "exportou vazio" de "esqueceu de exportar".
    ("user_preferences", "ui_settings"): {"tema": "escuro"},
}


def tabelas_ligadas_a_users() -> dict[str, sa.Table]:
    """Toda tabela que alcança `users` por chave estrangeira, direta ou não."""
    tabelas = Base.metadata.tables
    ligadas = {USERS}
    mudou = True
    while mudou:
        mudou = False
        for tabela in tabelas.values():
            if tabela.fullname in ligadas:
                continue
            if any(fk.column.table.fullname in ligadas for fk in tabela.foreign_keys):
                ligadas.add(tabela.fullname)
                mudou = True
    ligadas.discard(USERS)
    return {nome: tabelas[nome] for nome in ligadas}


def colunas_que_apontam_para_users() -> list[sa.Column]:
    return [
        fk.parent
        for tabela in Base.metadata.tables.values()
        for fk in tabela.foreign_keys
        if fk.column.table.fullname == USERS
    ]


def _valor_pelo_tipo(coluna: sa.Column):
    tipo = coluna.type
    if isinstance(tipo, postgresql.UUID | sa.Uuid):
        return uuid.uuid4()
    if isinstance(tipo, sa.Enum):
        return tipo.enums[0]
    if isinstance(tipo, sa.String):  # inclui Text
        texto = f"t-{uuid.uuid4().hex}"
        return texto[: tipo.length] if tipo.length else texto
    if isinstance(tipo, sa.Boolean):
        return True
    if isinstance(tipo, sa.Integer | sa.Numeric | sa.Float):
        return 1
    if isinstance(tipo, sa.DateTime):
        return datetime.now(UTC)
    if isinstance(tipo, sa.Date):
        return date.today()
    if isinstance(tipo, postgresql.JSONB | sa.JSON):
        return {"campo": "valor"}
    if isinstance(tipo, postgresql.ARRAY):
        return []
    if isinstance(tipo, postgresql.INET):
        return "10.0.0.1"
    if type(tipo).__name__.lower() == "vector":
        return [0.0] * tipo.dim
    raise NotImplementedError(
        f"fabrica_do_titular não sabe gerar valor para {coluna.table.fullname}.{coluna.name} "
        f"({tipo!r}). Acrescente o tipo em `_valor_pelo_tipo`."
    )


class _Construtor:
    def __init__(self, db, user_id):
        self.db = db
        self.user_id = user_id
        self.criadas: dict[str, dict] = {}  # tabela -> valores da linha criada

    async def garante(self, tabela: sa.Table) -> dict:
        if tabela.fullname in self.criadas:
            return self.criadas[tabela.fullname]

        valores = {}
        for coluna in tabela.columns:
            fixo = VALORES_FIXOS.get((tabela.fullname, coluna.name))
            if fixo is not None:
                valores[coluna.name] = fixo
                continue

            fk = next(iter(coluna.foreign_keys), None)
            if fk is not None:
                alvo = fk.column.table
                if alvo.fullname == USERS:
                    valores[coluna.name] = self.user_id
                elif alvo.fullname in self.criadas:
                    valores[coluna.name] = self.criadas[alvo.fullname][fk.column.name]
                elif not coluna.nullable and alvo is not tabela:
                    valores[coluna.name] = (await self.garante(alvo))[fk.column.name]
                continue

            if coluna.primary_key and isinstance(coluna.type, postgresql.UUID | sa.Uuid):
                valores[coluna.name] = uuid.uuid4()
                continue
            if coluna.default is not None or coluna.server_default is not None:
                # Com padrão: o schema sabe o valor válido melhor do que um gerador
                # por tipo (é onde moram os CHECK e os enums em texto).
                continue
            if coluna.primary_key and coluna.autoincrement in (True, "auto") and isinstance(coluna.type, sa.Integer):
                continue
            valores[coluna.name] = _valor_pelo_tipo(coluna)

        chaves = list(tabela.primary_key.columns)
        resultado = await self.db.execute(insert(tabela).values(**valores).returning(*chaves))
        linha = resultado.mappings().one()
        self.criadas[tabela.fullname] = {**valores, **dict(linha)}
        return self.criadas[tabela.fullname]


async def criar_usuario_completo(db, user) -> dict[str, dict]:
    """Popula toda tabela ligada a `user` e devolve {tabela: linha criada}."""
    construtor = _Construtor(db, user.id)
    ligadas = tabelas_ligadas_a_users()
    # `sorted_tables` entrega as mães antes das filhas.
    for tabela in Base.metadata.sorted_tables:
        if tabela.fullname in ligadas:
            await construtor.garante(tabela)
    await db.commit()
    return {nome: construtor.criadas[nome] for nome in ligadas}
