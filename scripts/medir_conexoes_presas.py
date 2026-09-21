"""
Mede se o stream ainda prende conexão de banco durante a resposta.

POR QUE ESTE SCRIPT EXISTE
O item mais grave da varredura de 2026-09-18 era o teto de ~20 respostas
simultâneas: cada `/orquestrador/stream` segurava DUAS conexões do início ao fim,
uma delas ociosa DENTRO de uma transação (`idle in transaction`) por toda a
geração do modelo — 13 a 57 segundos sem tocar no banco. A fase 4 do plano mudou
isso (commit antes de chamar o modelo). Só que o número de "antes" nunca foi
medido sob carga: o teto era aritmética sobre a configuração, não medição.

Este script é a medição que faltava, e ele mede o que separa "o código mudou" de
"o problema acabou": `idle in transaction` DURANTE uso real.

COMO LER O RESULTADO
- `idle in transaction` no pico perto de 0 → nenhuma conexão presa esperando o
  modelo. É o esperado depois da fase 4.
- Vários simultâneos, subindo junto com o movimento → alguma transação voltou a
  ficar aberta esperando I/O. Os suspeitos, nesta ordem: `/orquestrador/query`
  (que AINDA espera o modelo dentro da transação — por isso está obsoleta),
  `/agregador/stream` (mesmo defeito, registrado e não corrigido), ou um caminho
  novo que abriu transação antes de uma chamada externa.
- `esperando bloqueio` > 0 de forma persistente → duas transações disputando a
  mesma linha; foi o sintoma do travamento do contador semanal (item 19).

QUANDO RODAR
Num horário de movimento — com médicos usando o produto. Num banco parado o
resultado é sempre zero e não prova nada.

    python -m scripts.medir_conexoes_presas                 # 5 min, amostra a cada 2 s
    python -m scripts.medir_conexoes_presas --minutos 30
    python -m scripts.medir_conexoes_presas --csv medicao.csv

SÓ LÊ `pg_stat_activity`. Não escreve, não altera sessão de ninguém.
"""

import argparse
import asyncio
import csv
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.database import engine  # noqa: E402

# `app_debug=true` liga o eco do SQLAlchemy e enterra a tabela do script no SQL
# das próprias consultas. Aqui a saída É o produto; silencia o eco.
engine.echo = engine.sync_engine.echo = False

CONSULTA = text("""
    SELECT
      count(*) FILTER (WHERE state = 'active')                        AS ativas,
      count(*) FILTER (WHERE state LIKE 'idle in transaction%')       AS presas,
      count(*) FILTER (WHERE wait_event_type = 'Lock')               AS esperando,
      count(*)                                                        AS total,
      coalesce(max(EXTRACT(EPOCH FROM (now() - xact_start)))
               FILTER (WHERE state LIKE 'idle in transaction%'), 0)   AS presa_ha_segundos
    FROM pg_stat_activity
    WHERE datname = current_database()
      AND pid <> pg_backend_pid()
""")


async def medir(minutos: float, intervalo: float, caminho_csv: str | None) -> int:
    fim = time.monotonic() + minutos * 60
    amostras: list[dict] = []
    pico = Counter()
    pior_presa = 0.0

    print(f"Medindo por {minutos:g} min, uma amostra a cada {intervalo:g}s. Ctrl+C encerra e resume.\n")
    print(f"{'hora':8s} {'ativas':>7s} {'presas':>7s} {'esperando':>10s} {'total':>6s}  {'presa há':>9s}")
    print("-" * 56)

    try:
        while time.monotonic() < fim:
            async with engine.connect() as conn:
                linha = (await conn.execute(CONSULTA)).mappings().one()

            agora = datetime.now(UTC)
            amostras.append({"momento": agora.isoformat(), **dict(linha)})
            for chave in ("ativas", "presas", "esperando", "total"):
                pico[chave] = max(pico[chave], linha[chave])
            pior_presa = max(pior_presa, float(linha["presa_ha_segundos"]))

            alerta = "  <-- conexão presa" if linha["presas"] else ""
            print(
                f"{agora.astimezone().strftime('%H:%M:%S')} {linha['ativas']:7d} "
                f"{linha['presas']:7d} {linha['esperando']:10d} {linha['total']:6d}  "
                f"{float(linha['presa_ha_segundos']):8.1f}s{alerta}"
            )
            await asyncio.sleep(intervalo)
    except KeyboardInterrupt:
        print("\n(interrompido)")
    finally:
        await engine.dispose()

    if not amostras:
        print("Nenhuma amostra coletada.")
        return 1

    print("\n" + "=" * 56)
    print(f"{len(amostras)} amostras")
    print(f"  pico de conexões ATIVAS ......... {pico['ativas']}")
    print(f"  pico de conexões PRESAS ......... {pico['presas']}   (idle in transaction)")
    print(f"  pico esperando bloqueio ......... {pico['esperando']}")
    print(f"  pico de conexões no total ....... {pico['total']}")
    print(f"  transação presa por mais tempo .. {pior_presa:.1f}s")
    print()

    # A ORDEM IMPORTA: conexão presa é conclusiva mesmo sem movimento — foi assim
    # que a primeira versão deste script viu uma transação parada por 9s e mesmo
    # assim respondeu "não prova nada".
    if pior_presa >= 2:
        print(f"VEREDITO: ATENÇÃO — conexão presa por {pior_presa:.0f}s. Esse é o tempo de")
        print("uma chamada de modelo: alguma transação está aberta esperando I/O externo.")
        print("Suspeitos: /orquestrador/query (obsoleta), /agregador/stream (débito")
        print("registrado) ou caminho novo. Ver docs/pendencias.md.")
        veredito = 2
    elif pico["ativas"] == 0 and pico["presas"] == 0:
        print("VEREDITO: o banco ficou parado o tempo todo. Sem uso real, a medição não")
        print("prova nada — rode de novo num horário com médicos usando o produto.")
        veredito = 1
    elif pico["presas"] == 0:
        print("VEREDITO: nenhuma conexão presa em transação durante o uso. É o esperado")
        print("depois da fase 4 — o stream solta a conexão antes de chamar o modelo.")
        veredito = 0
    else:
        print("VEREDITO: houve transação aberta, mas por menos de 2s — é escrita normal,")
        print("não espera por modelo. Sem sinal do defeito antigo.")
        veredito = 0

    if caminho_csv:
        with open(caminho_csv, "w", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=list(amostras[0]))
            escritor.writeheader()
            escritor.writerows(amostras)
        print(f"\nAmostras em {caminho_csv}")
    return veredito


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Mede conexões presas em transação durante uso real.")
    p.add_argument("--minutos", type=float, default=5)
    p.add_argument("--intervalo", type=float, default=2)
    p.add_argument("--csv", dest="caminho_csv", default=None)
    a = p.parse_args()
    sys.exit(asyncio.run(medir(a.minutos, a.intervalo, a.caminho_csv)))
