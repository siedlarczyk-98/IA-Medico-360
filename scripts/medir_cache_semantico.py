"""
Mede o cache semântico antes de mexer no índice vetorial.

Existe porque o índice ivfflat de `semantic_cache` foi criado na migration de
baseline, com a tabela VAZIA. ivfflat calcula os centroides no momento da
criação: sem dados, eles não representam nada, e o recall fica ruim até alguém
reindexar. O sintoma é silencioso — não há erro, só respostas que deveriam ser
instantâneas custando uma chamada de modelo.

`lists` também importa: a regra prática é `lists ≈ √n`. O baseline fixou 100,
que corresponde a ~10.000 linhas.

Este script NÃO altera nada. Ele responde três perguntas:
  1. Quantas linhas o cache tem hoje (decide entre dropar o índice e migrar).
  2. Qual a taxa de acerto por modo, das interações recentes.
  3. Como os acertos se distribuem (poucas entradas quentes ou cauda longa).

Execute via: python -m scripts.medir_cache_semantico [dias]
"""

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

# Só estes dois modos consultam o cache — ver o gate em
# `orquestrador_stream_service`. Incluir os outros dilui a taxa com interações
# que nunca poderiam ter acertado.
MODOS_CACHEAVEIS = ("QUICK_SEARCH", "CLINICAL_REASONING")


async def medir(dias: int) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.connect() as conn:
        total = (await conn.execute(
            text("SELECT COUNT(*) FROM semantic_cache")
        )).scalar_one()

        vivos = (await conn.execute(
            text("SELECT COUNT(*) FROM semantic_cache WHERE expires_at > NOW()")
        )).scalar_one()

        print("\n=== semantic_cache ===")
        print(f"entradas totais    : {total}")
        print(f"entradas nao vencidas: {vivos}")
        print(f"lists ideal (~sqrt n): {int(max(1, vivos ** 0.5))}  (o baseline fixou 100)")

        print(f"\n=== taxa de acerto, ultimos {dias} dias ===")
        linhas = (await conn.execute(text("""
            SELECT mode,
                   COUNT(*)                                   AS total,
                   COUNT(*) FILTER (WHERE cache_hit)          AS acertos
              FROM interactions
             WHERE feature = 'ORQUESTRADOR'
               AND mode = ANY(:modos)
               AND created_at > NOW() - make_interval(days => :dias)
             GROUP BY mode
             ORDER BY total DESC
        """), {"modos": list(MODOS_CACHEAVEIS), "dias": dias})).all()

        if not linhas:
            print("(nenhuma interacao cacheavel no periodo)")
        for modo, tot, acertos in linhas:
            pct = (acertos / tot * 100) if tot else 0.0
            print(f"{modo:20s} {acertos:6d}/{tot:<6d}  {pct:5.1f}%")

        print("\n=== distribuicao dos acertos por entrada ===")
        dist = (await conn.execute(text("""
            SELECT hit_count, COUNT(*)
              FROM semantic_cache
             GROUP BY hit_count
             ORDER BY hit_count
             LIMIT 15
        """))).all()
        for hits, quantas in dist:
            print(f"  {hits:4d} acerto(s): {quantas} entrada(s)")

        print("\n=== leitura ===")
        if vivos < 1000:
            print("Poucas linhas. Um scan sequencial e mais rapido E exato que o")
            print("ivfflat atual — considere DROPAR o indice e recria-lo (HNSW)")
            print("quando a tabela crescer.")
        else:
            print("Volume suficiente para indice. O ivfflat foi construido vazio,")
            print("entao o recall provavelmente esta abaixo do possivel: migre")
            print("para HNSW, que nao depende de dados previos nem de reindexacao.")

    await engine.dispose()


if __name__ == "__main__":
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    asyncio.run(medir(dias))
