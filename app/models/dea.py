"""
Médico 360 — Modelos do localizador de DEA (schema `dea`).

DEA = Desfibrilador Externo Automático.

Este é o único módulo do produto que é **público**: qualquer pessoa consulta e
cadastra, sem login. Duas consequências percorrem o arquivo inteiro:

1. Nenhuma FK para `users`. O autor de um registro é identificado por um hash
   rotativo de IP (ver `criado_por_ip_hash`), nunca por conta.
2. Nada é deletado. "Alguém foi lá e não achou" é informação valiosa — vira
   `status`, não `DELETE`.

## A decisão central: confiança que envelhece

O protótipo que originou o projeto tinha um `verified: bool`. Booleano não
envelhece: um DEA "verificado" em 2026 continua verificado em 2029, mesmo que
tenha sido removido da parede em 2027. Correr 300 m até um DEA que não existe
mais é tempo fora da janela de sobrevida.

Por isso a verificação virou **histórico** (`Verificacao`), e a confiança é
derivada dele — decaindo sozinha com o tempo. A regra de produto que decorre
disso: o app nunca diz "há um DEA aqui", diz "registrado, confirmado por 3
pessoas, última verificação há 12 dias".

## Por que `String` e não Enum nativo do Postgres

Mesma razão documentada em `app/models/news.py` e em
`docs/ARQUITETURA_TECNICA.md` §11.1: campos categóricos são `VARCHAR` validados
na aplicação. Um `CREATE TYPE` exigiria `ALTER TYPE` a cada status novo — e
neste módulo vamos acrescentar status (spam, moderado, importado...).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.models import new_uuid, utcnow

SCHEMA = "dea"


class AcessoEnum(str, enum.Enum):
    """Quão acessível o aparelho é para quem chega correndo.

    É a informação que mais separa um DEA útil de um inútil — mais até que o
    horário. Um aparelho atrás de uma recepção às 3h da manhã é um aparelho que,
    na prática, não existe.
    """

    PUBLICO_LIVRE = "publico_livre"
    BALCAO_RECEPCAO = "balcao_recepcao"
    RESTRITO_FUNCIONARIOS = "restrito_funcionarios"


class StatusDispositivoEnum(str, enum.Enum):
    """Ciclo de vida do registro. Nada aqui significa "linha apagada".

    `PENDENTE` é etiqueta de confiança, não quarentena: o pin aparece no mapa
    desde o primeiro instante, visualmente distinto, e é promovido quando outra
    pessoa confirma. Segurar o pin até alguém confirmar mataria a contribuição
    justamente onde ela é mais valiosa — um bairro sem nenhum usuário.
    """

    PENDENTE = "pendente"
    ATIVO = "ativo"
    NAO_ENCONTRADO = "nao_encontrado"
    REMOVIDO = "removido"
    SPAM = "spam"


class OrigemEnum(str, enum.Enum):
    COLABORATIVO = "colaborativo"
    OFICIAL = "oficial"
    IMPORTADO = "importado"


class ResultadoVerificacaoEnum(str, enum.Enum):
    ENCONTRADO = "encontrado"
    NAO_ENCONTRADO = "nao_encontrado"
    REMOVIDO = "removido"


class Local(Base):
    """O estabelecimento: shopping, estação, academia, prédio.

    Separado de `Dispositivo` por dois motivos práticos, nenhum deles
    especulativo:

    - **Correção de endereço.** O endereço é do prédio, não do aparelho. Sem esta
      tabela, corrigir "na verdade é rua X, 200" exigiria atualizar N linhas, que
      inevitavelmente divergiriam.
    - **Duplicata.** É o problema nº 1 de mapa colaborativo: duas pessoas
      cadastram o mesmo shopping. Com `Local`, fundir é repontar `local_id`. Sem
      ele, é impossível fundir sem perder dado.

    O cadastro do v1 cria local + 1 dispositivo numa transação, e a interface não
    expõe o conceito. A tabela existe para o dia da fusão, não para a tela.
    """

    __tablename__ = "locais"
    __table_args__ = (
        # Busca por raio: pré-filtro de bounding box usa este índice.
        #
        # Btree comum, DECLARADO NO MODELO de propósito. `tests/conftest.py` monta
        # o schema com `Base.metadata.create_all`, então índice criado só por SQL
        # cru na migration não existiria no banco de teste — e o teste da busca
        # deixaria de exercitar o caminho de produção. Foi o argumento decisivo
        # contra PostGIS/earthdistance aqui: com alguns milhares de DEAs, o ganho
        # de um índice espacial não paga a divergência.
        Index("ix_dea_locais_lat_lon", "latitude", "longitude"),
        # Detecção de duplicata: ~11 m de resolução, granularidade de "mesmo
        # prédio". Não é UNIQUE — dois prédios vizinhos podem cair na mesma
        # célula, e recusar o cadastro seria pior que ter o que fundir depois.
        Index("ix_dea_locais_dedupe", "lat_arredondada", "lon_arredondada"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)

    # Texto livre, opcional: a coordenada vem do clique no mapa, não daqui. Serve
    # para exibição e busca textual futura — nunca para localizar.
    endereco: Mapped[str | None] = mapped_column(String(240))
    cidade: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Materializadas para o índice de dedupe. Recalculadas junto com lat/lon.
    lat_arredondada: Mapped[float] = mapped_column(Float, nullable=False)
    lon_arredondada: Mapped[float] = mapped_column(Float, nullable=False)

    # Texto livre, EXIBIDO E NUNCA INTERPRETADO ("Seg-Sáb 10h-22h, Dom 14h-20h").
    #
    # A versão estruturada (tabela de janelas por dia) foi descartada: sete linhas
    # de dia/abre/fecha é onde a contribuição morre num formulário de celular, o
    # campo ficaria 95% vazio, e "vazio" seria indistinguível de "24 h". Pior:
    # horário desatualizado com cara de exato é o modo de falha mais perigoso
    # aqui. Se o uso real mostrar que o dado existe e é consultado, estruturar
    # depois — com dado para desenhar o formato em vez de adivinhar.
    horario_texto: Mapped[str | None] = mapped_column(String(200))

    # O booleano resolve sozinho a pergunta que mais importa, sem modelar agenda.
    acesso_24h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    dispositivos: Mapped[list["Dispositivo"]] = relationship(back_populates="local", cascade="all, delete-orphan")


class Dispositivo(Base):
    """Um aparelho DEA dentro de um local. Um aeroporto tem vários."""

    __tablename__ = "dispositivos"
    __table_args__ = (
        Index("ix_dea_dispositivos_local_status", "local_id", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    local_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.locais.id", ondelete="CASCADE"), nullable=False)

    # O campo que mais economiza segundos: "térreo, parede ao lado do caixa 3"
    # vale mais que seis casas decimais de GPS para quem já chegou no prédio.
    descricao_localizacao: Mapped[str | None] = mapped_column(Text)

    acesso: Mapped[str] = mapped_column(String(30), default=AcessoEnum.PUBLICO_LIVRE.value, nullable=False)

    # Permite validar à distância e é o que o socorrista reconhece correndo.
    foto_url: Mapped[str | None] = mapped_column(String(500))

    status: Mapped[str] = mapped_column(String(20), default=StatusDispositivoEnum.PENDENTE.value, nullable=False)
    origem: Mapped[str] = mapped_column(String(20), default=OrigemEnum.COLABORATIVO.value, nullable=False)

    # Contadores materializados a partir de `verificacoes`, atualizados na mesma
    # transação que insere a verificação.
    #
    # `COUNT` + `MAX` correlacionados por dispositivo, dentro de uma busca por
    # raio que já varre uma bounding box, ficam lentos com pouco dado. A tabela
    # `verificacoes` continua sendo a fonte de verdade auditável — estes campos
    # são cache, e podem ser recomputados a partir dela.
    verificacoes_positivas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verificacoes_negativas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ultima_verificacao_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Hash rotativo do IP de quem cadastrou — nunca o IP em claro. Serve para
    # impedir que a mesma origem confirme o próprio registro, e para rate limit.
    # Ver `app/dea/services/anonimato.py` para o esquema do hash e o porquê do
    # bucket diário.
    criado_por_ip_hash: Mapped[str | None] = mapped_column(String(64))

    local: Mapped["Local"] = relationship(back_populates="dispositivos")
    verificacoes: Mapped[list["Verificacao"]] = relationship(back_populates="dispositivo", cascade="all, delete-orphan")


class Verificacao(Base):
    """Registro de que alguém foi até o local e olhou.

    É o que mantém o mapa vivo: sem um fluxo barato de "estou aqui, encontrei /
    não encontrei", a base vira um cemitério de pins de 2026.

    Guardamos o histórico inteiro, inclusive as negativas — duas negativas
    seguidas dizem mais sobre o aparelho do que dez positivas antigas.
    """

    __tablename__ = "verificacoes"
    __table_args__ = (
        Index("ix_dea_verificacoes_dispositivo", "dispositivo_id", "verificado_em"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    dispositivo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.dispositivos.id", ondelete="CASCADE"), nullable=False
    )
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text)
    verificado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ip_hash: Mapped[str | None] = mapped_column(String(64))

    dispositivo: Mapped["Dispositivo"] = relationship(back_populates="verificacoes")
