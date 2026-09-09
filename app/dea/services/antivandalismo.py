"""
Defesas da escrita pública do mapa de DEA.

Cadastrar não exige login, então não há conta para responsabilizar depois. As
camadas abaixo estão em ordem de **eficácia real**, não de sofisticação:

1. **Densidade geográfica** — a única que não depende de identificar a origem, e
   por isso a mais confiável aqui.
2. **`status=pendente`** — não bloqueia nada, mas tira o incentivo: um pin
   plantado nasce marcado como não confirmado e não convence ninguém.
3. **Honeypot e tempo mínimo** — pegam bot genérico de formulário, que é a maior
   parte do volume automatizado.
4. **Limite por origem** — o mais fácil de contornar, ver abaixo.

## Por que o limite por origem vem por último

O container roda uvicorn com `--forwarded-allow-ips "*"` (ver `Dockerfile`), o
que faz o ASGI aceitar `X-Forwarded-For` de qualquer peer. Trocar esse header a
cada requisição rende origem nova a cada vez. Enquanto isso não for corrigido —
trabalho à parte, que também afeta login e OTP — o limite por origem é redutor
de ruído acidental, não barreira contra ataque dirigido.

Registrar isso aqui é o ponto: uma defesa em que se confia mais do que ela
merece é pior que uma defesa ausente.
"""

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dea.repositories.locais_repository import bounding_box
from app.services import cache_service

# Janela do limite de densidade.
JANELA_DENSIDADE = timedelta(hours=1)

# Raio, em km, da vizinhança considerada no limite de densidade. ~1 km é o
# tamanho de um bairro pequeno: grande o bastante para pegar um script plantando
# pins numa área, pequeno o bastante para não punir uma cidade inteira.
RAIO_DENSIDADE_KM = 1.0

# Abaixo disto, o formulário foi preenchido rápido demais para ser humano.
SEGUNDOS_MINIMOS_DE_PREENCHIMENTO = 3


SQL_DENSIDADE = text(
    """
    SELECT count(*)
    FROM dea.locais
    -- O intervalo vai como número de segundos e é montado aqui, em vez de
    -- passado como `interval`: o asyncpg envia parâmetros sem tipo declarado, e
    -- o Postgres não infere `interval` nesta posição — a consulta falha com
    -- "operator does not exist: timestamp with time zone > interval".
    WHERE criado_em > (now() - make_interval(secs => :janela_segundos))
      AND latitude  BETWEEN :lat_min AND :lat_max
      AND longitude BETWEEN :lon_min AND :lon_max
    """
)


async def densidade_excedida(
    db: AsyncSession,
    *,
    latitude: float,
    longitude: float,
    maximo_por_hora: int,
) -> bool:
    """Já houve cadastros demais nesta vizinhança na última hora?

    Mata o ataque que realmente estraga o mapa: dezenas de pins falsos numa
    quadra. Usa o mesmo índice `(latitude, longitude)` da busca.

    **Conta apenas locais novos, nunca verificações.** É a diferença entre
    barrar spam e barrar o caso de uso principal: trinta alunos confirmando o
    mesmo DEA durante um curso de ACLS é exatamente o comportamento desejado, e
    tratá-lo como ataque mataria o canal de captação.
    """
    lat_min, lat_max, lon_min, lon_max = bounding_box(latitude, longitude, RAIO_DENSIDADE_KM)
    resultado = await db.execute(
        SQL_DENSIDADE,
        {
            "janela_segundos": JANELA_DENSIDADE.total_seconds(),
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lon_min": lon_min,
            "lon_max": lon_max,
        },
    )
    return (resultado.scalar() or 0) >= maximo_por_hora


async def limite_por_origem_excedido(escopo: str, ip_hash: str, limite: int, janela_segundos: int) -> bool | None:
    """Limite por origem, em Redis (compartilhado entre réplicas).

    Devolve `True` (excedeu), `False` (dentro do limite) ou **`None` quando o
    Redis está indisponível** — e essa terceira resposta é o ponto do desenho.

    `cache_service.rate_limit_exceeded` falha *aberto*, o que é a escolha certa
    para login (derrubar a autenticação porque o cache caiu seria pior que o
    risco). Para escrita pública anônima o cálculo se inverte: Redis fora com
    fail-open é janela livre de spam. Mas fail-closed puro também é ruim — a
    contribuição legítima seria perdida por uma indisponibilidade que não é
    culpa de quem contribui.

    Por isso a terceira via: o chamador aceita a submissão e a força a nascer
    `pendente`. Nada se perde, e nada entra no mapa sem revisão.
    """
    chave = cache_service.make_key(f"ratelimit:dea:{escopo}", ip_hash)
    try:
        return await cache_service.rate_limit_exceeded(chave, limite, janela_segundos)
    except Exception:
        return None


def parece_bot(*, honeypot: str | None, segundos_de_preenchimento: float | None) -> bool:
    """Sinais baratos de automação.

    - **Honeypot**: campo escondido por CSS que humano nenhum enxerga. Bot
      genérico preenche tudo que encontra.
    - **Tempo de preenchimento**: quem digitou nome, endereço e localização em
      menos de três segundos não digitou.

    Nenhum dos dois é conclusivo isoladamente, e é por isso que a resposta a eles
    não é erro — ver `app/dea/routers/dea_router.py`.
    """
    if honeypot:
        return True
    if segundos_de_preenchimento is not None and segundos_de_preenchimento < SEGUNDOS_MINIMOS_DE_PREENCHIMENTO:
        return True
    return False
