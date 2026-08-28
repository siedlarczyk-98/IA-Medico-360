"""
Diagnóstico: as garantias silenciosas do sistema continuam valendo?

NÃO ESCREVE NADA. Só faz SELECT (três COUNT e duas somas). Pode ser apontado
para produção sem risco de alteração.

    python -m scripts.verificar_vigilancia

Sai com código 1 quando alguma medição vira alarme.

QUANDO USAR
A vigilância roda sozinha, dentro do backend, a cada 6h — ver
`app/services/vigilancia_agendada.py`. Este script existe para responder à mão
"como está agora?", sem esperar o próximo ciclo e sem disparar alarme nenhum:
útil depois de um deploy, ao investigar uma conta de API mais alta que o
esperado, ou para conferir um ambiente que ficou parado.

As medições vêm de `vigilancia_service` — as MESMAS que a tarefa agendada usa.
Duas contagens diferentes para a mesma pergunta acabariam divergindo, e a
divergência apareceria como um dos dois mentindo. Mesmo motivo pelo qual
`verificar_expurgo.py` reusa `medir_passivo`.
"""

import asyncio
import logging
import sys

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.logging_config import setup_logging
from app.services.vigilancia_service import (
    MIN_AMOSTRA_CACHE,
    avaliar,
    medir_tudo,
)

logger = logging.getLogger("scripts.verificar_vigilancia")


async def main() -> int:
    settings = get_settings()
    setup_logging(level=settings.log_level, json_output=settings.is_production)

    async with async_session_factory() as db:
        m = await medir_tudo(db)

    cache, custo, expurgo = m["cache"], m["custo"], m["expurgo"]

    print(f"Vigilância — janela de {cache['janela_dias']} dias\n")

    print("Cache semântico")
    print(f"  interações elegíveis      : {cache['elegiveis']}")
    print(f"  servidas do cache         : {cache['hits']} ({cache['taxa_hit']:.1%})")
    print(f"  entradas vigentes na tabela: {cache['linhas_vigentes']}")
    if cache["elegiveis"] < MIN_AMOSTRA_CACHE:
        print(f"  (amostra abaixo de {MIN_AMOSTRA_CACHE} — sem volume para concluir nada)")

    print("\nCusto de modelo")
    print(f"  janela atual              : US$ {custo['custo_usd']:.2f}")
    print(f"  janela anterior           : US$ {custo['custo_usd_anterior']:.2f}")
    if custo["fator"] is not None:
        print(f"  variação                  : {custo['fator']:.2f}x")

    print("\nExpurgo de retenção")
    if expurgo["nunca_registrado"]:
        print("  última rodada             : nenhuma registrada")
    else:
        print(f"  última rodada             : {expurgo['ultimo_em']} ({expurgo['dias_desde']}d atrás)")

    alarmes = avaliar(m)
    if not alarmes:
        print("\nOK — nenhuma medição em nível de alarme.")
        logger.info("Vigilância em dia", extra=m)
        return 0

    print(f"\n{len(alarmes)} ALARME(S):")
    for a in alarmes:
        print(f"\n  [{a['tag']}]")
        print(f"  {a['mensagem']}")

    print("\nNo Sentry, procure pela tag alarme=<nome> acima.")
    logger.warning("Vigilância encontrou alarmes", extra={"tags": [a["tag"] for a in alarmes]})
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
