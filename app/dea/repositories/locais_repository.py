"""
Busca geográfica de locais com DEA.

## Por que Haversine à mão, e não PostGIS

Não há extensão geoespacial neste banco, e a decisão de não adicionar uma foi
deliberada. O argumento decisivo não é performance, é **testabilidade**:
`tests/conftest.py` monta o schema com `Base.metadata.create_all`, não com
Alembic. Um índice GiST sobre `earth_box(...)`, ou a própria extensão, seriam
criados apenas pela migration — e portanto não existiriam no banco de teste. O
teste da busca passaria exercitando um caminho diferente do de produção, que é
pior do que não ter teste.

Somam-se dois pontos: `CREATE EXTENSION` pode ser recusado num Postgres
gerenciado (descoberto no deploy, no meio da cadeia de migrations), e o ganho de
um índice espacial só aparece com centenas de milhares de pontos. Com alguns
milhares de DEAs no Brasil, um scan sobre a bounding box é questão de
milissegundos.

Precisão: a diferença entre esfera e elipsoide é ~0,3% — seis metros num raio de
dois quilômetros. O erro do GPS do celular é maior que isso, e o erro do "acho
que era no térreo" é ordens de grandeza maior.

## A busca em duas fases, numa ida só ao banco

1. **Bounding box** (usa o índice btree `(latitude, longitude)`): descarta a
   quase totalidade das linhas com comparação de números.
2. **Haversine** sobre o que sobrou: distância real, ordenação e corte.
"""

import math

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Raio médio da Terra, em km — o mesmo valor usado do lado do cliente.
RAIO_TERRA_KM = 6371.0

# Um grau de latitude tem ~111,045 km em qualquer lugar. Longitude encolhe com o
# cosseno da latitude.
KM_POR_GRAU_LAT = 111.045

# Piso para o cosseno no cálculo do delta de longitude. Perto dos polos o
# cosseno tende a zero e o delta explodiria; no Brasil isso nunca acontece, mas
# custa nada e evita um dia estranho.
COS_MINIMO = 0.01

SQL_BUSCA_POR_RAIO = text(
    """
    WITH candidatos AS (
        -- Fase 1: bounding box. Barata e indexada.
        SELECT id, nome, endereco, cidade, uf, latitude, longitude,
               horario_texto, acesso_24h, criado_em
        FROM dea.locais
        WHERE latitude  BETWEEN :lat_min AND :lat_max
          AND longitude BETWEEN :lon_min AND :lon_max
    )
    -- Fase 2: distância real sobre o que sobrou.
    SELECT c.*,
           (:raio_terra * 2 * asin(sqrt(
               power(sin(radians(c.latitude - :lat) / 2), 2)
               + cos(radians(:lat)) * cos(radians(c.latitude))
               * power(sin(radians(c.longitude - :lon) / 2), 2)
           ))) AS distancia_km
    FROM candidatos c
    WHERE (:raio_terra * 2 * asin(sqrt(
               power(sin(radians(c.latitude - :lat) / 2), 2)
               + cos(radians(:lat)) * cos(radians(c.latitude))
               * power(sin(radians(c.longitude - :lon) / 2), 2)
           ))) <= :raio_km
    ORDER BY distancia_km
    LIMIT :limite
    """
)


def bounding_box(latitude: float, longitude: float, raio_km: float) -> tuple[float, float, float, float]:
    """Retângulo que contém o círculo de raio `raio_km`.

    Devolve `(lat_min, lat_max, lon_min, lon_max)`. É intencionalmente generoso:
    o retângulo contém área fora do círculo, e o refino de Haversine descarta
    essa sobra.
    """
    delta_lat = raio_km / KM_POR_GRAU_LAT
    cos_lat = max(abs(math.cos(math.radians(latitude))), COS_MINIMO)
    delta_lon = raio_km / (KM_POR_GRAU_LAT * cos_lat)

    return (
        latitude - delta_lat,
        latitude + delta_lat,
        longitude - delta_lon,
        longitude + delta_lon,
    )


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine em Python — mesma fórmula do SQL acima.

    Existe para os testes poderem conferir o resultado do banco contra um cálculo
    independente, e para ordenação em memória quando já se tem os dados.
    """
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return RAIO_TERRA_KM * 2 * math.asin(math.sqrt(a))


async def buscar_por_raio(
    db: AsyncSession,
    *,
    latitude: float,
    longitude: float,
    raio_km: float,
    limite: int,
) -> list[dict]:
    """Locais dentro do raio, do mais próximo ao mais distante.

    Todos os parâmetros são ligados (`:nome`), nunca interpolados: é rota
    pública, e um float vindo de fora pode ser `nan`, `inf` ou notação
    científica. O teto de `raio_km` e `limite` é aplicado no schema Pydantic da
    rota — sem ele, `raio_km=20000` seria um dump do banco inteiro.
    """
    lat_min, lat_max, lon_min, lon_max = bounding_box(latitude, longitude, raio_km)

    resultado = await db.execute(
        SQL_BUSCA_POR_RAIO,
        {
            "lat": latitude,
            "lon": longitude,
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lon_min": lon_min,
            "lon_max": lon_max,
            "raio_km": raio_km,
            "raio_terra": RAIO_TERRA_KM,
            "limite": limite,
        },
    )
    return [dict(linha) for linha in resultado.mappings()]
