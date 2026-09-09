"""
Schemas de entrada e saída do localizador de DEA.

Como o módulo é público e sem login, os limites daqui são a primeira barreira
real — não há sessão para responsabilizar depois.
"""

import uuid

from pydantic import BaseModel, Field

from app.models.dea import AcessoEnum, ResultadoVerificacaoEnum

# Teto do raio de busca. Sem ele, `raio_km=20000` devolveria o banco inteiro por
# uma rota pública — o jeito mais barato de raspar a base que existe.
RAIO_MAXIMO_KM = 25.0
RAIO_PADRAO_KM = 5.0

# Idem para a quantidade. O SQL também tem `LIMIT` incondicional.
LIMITE_MAXIMO = 50
LIMITE_PADRAO = 20


class DispositivoOut(BaseModel):
    """Um aparelho, como a interface o consome."""

    id: uuid.UUID
    descricao_localizacao: str | None
    acesso: str
    foto_url: str | None
    status: str

    # Fatos crus, deliberadamente sem um score agregado: um número viraria
    # porcentagem em alguma tela, e porcentagem parece medida. Ver o docstring de
    # `app/dea/services/confianca.py`.
    confianca: str
    confirmacoes: int
    contestacoes: int
    dias_desde_ultima_verificacao: int | None


class LocalOut(BaseModel):
    id: uuid.UUID
    nome: str
    endereco: str | None
    cidade: str | None
    uf: str | None
    latitude: float
    longitude: float
    horario_texto: str | None
    acesso_24h: bool
    distancia_km: float
    dispositivos: list[DispositivoOut]


class BuscaResponse(BaseModel):
    """Resposta da busca por raio.

    `total` é o que veio nesta página, não o universo: com `LIMIT` aplicado, um
    total global exigiria uma segunda varredura e não muda nenhuma decisão de
    quem está procurando o DEA mais próximo.
    """

    locais: list[LocalOut]
    total: int
    raio_km: float

    # Repetido em toda resposta de propósito: qualquer cliente que consuma esta
    # API — inclusive um que não seja nosso — recebe junto a instrução que
    # precede o uso do mapa.
    aviso: str = (
        "Em parada cardiorrespiratória, ligue 192 (SAMU) e inicie as compressões. "
        "Os registros são colaborativos e podem estar desatualizados."
    )


class Coordenada(BaseModel):
    """Validação de lat/lon. Não é sobre geografia — é sobre não deixar entrar
    lixo por uma rota aberta."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


# ── Escrita ──────────────────────────────────────────────────────────────
#
# Todos os campos de texto têm teto de tamanho. Numa rota sem login, um `Text`
# sem limite é upload de arquivo disfarçado de formulário.


class CadastroRequest(BaseModel):
    """Cadastro de um DEA. Cria local + primeiro dispositivo numa transação.

    A interface não expõe o conceito de "local": quem cadastra descreve um
    aparelho num lugar. A separação existe no banco para poder fundir duplicatas
    depois — ver o docstring de `app/models/dea.py`.
    """

    nome: str = Field(min_length=2, max_length=160)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    # Texto livre e opcional: a coordenada vem do clique no mapa, não daqui.
    # Serve para exibição, nunca para localizar.
    endereco: str | None = Field(default=None, max_length=240)
    cidade: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, max_length=2)

    # O campo que mais economiza segundos de quem já chegou ao prédio.
    descricao_localizacao: str | None = Field(default=None, max_length=500)
    acesso: AcessoEnum = AcessoEnum.PUBLICO_LIVRE

    horario_texto: str | None = Field(default=None, max_length=200)
    acesso_24h: bool = False

    # ── Sinais antivandalismo ──
    # Campo escondido por CSS: humano não vê, bot genérico preenche. Nomeado
    # `website` porque é o nome que os bots mais procuram.
    website: str | None = Field(default=None, max_length=200)
    # Quanto tempo o formulário ficou aberto. Menos de 3s não é digitação.
    segundos_de_preenchimento: float | None = Field(default=None, ge=0)


class VerificacaoRequest(BaseModel):
    """ "Estou aqui: encontrei / não encontrei."

    É o motor de manutenção da base. Sem um fluxo barato como este, o mapa vira
    um cemitério de pins de 2026.
    """

    resultado: ResultadoVerificacaoEnum
    observacao: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=200)


class CadastroResponse(BaseModel):
    local_id: uuid.UUID
    dispositivo_id: uuid.UUID
    status: str
    mensagem: str


class VerificacaoResponse(BaseModel):
    dispositivo_id: uuid.UUID
    status: str
    confianca: str
    confirmacoes: int
    contestacoes: int
    mensagem: str
