"""
Schemas de entrada e saída do localizador de DEA.

Como o módulo é público e sem login, os limites daqui são a primeira barreira
real — não há sessão para responsabilizar depois.
"""

import uuid

from pydantic import BaseModel, Field

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
