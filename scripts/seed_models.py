"""
Fonte de verdade da tabela `model_pricing` — idempotente.

POR QUE EXISTE
Nenhuma migration insere linhas em `model_pricing`, e os scripts `add_*.py`
recebem o preço por argumento: os valores viviam SÓ no banco de produção. Um
banco restaurado do schema (ou um ambiente novo) respondia "Modelo X não
disponível" em todos os modos — e o backup do projeto é manual. Com custo zero
silencioso como efeito colateral: `calculate_cost` devolve 0 para modelo sem
preço, e o teto semanal beta deixa de contar.

A verdade agora é `scripts/dados/model_pricing.json`, versionado. Para atualizar
um preço: edite o JSON e rode este script. `tests/test_seed_models.py` exige que
todo modelo citado em `MODE_MODEL_MAP` e `FALLBACK_MODELS` esteja lá.

Para EXPORTAR o que está em produção para o JSON (uma vez, ou para conferir):

    SELECT json_agg(json_build_object(
        'model_id', model_id, 'provider', provider, 'provider_type', provider_type,
        'display_name', display_name,
        'input_per_million', input_per_million::text,
        'output_per_million', output_per_million::text,
        'status', status) ORDER BY model_id)
    FROM model_pricing;

Uso:
    python scripts/seed_models.py            # aplica
    python scripts/seed_models.py --conferir # só mostra a diferença, não grava

Não desativa nem apaga modelo que esteja no banco e fora do JSON — só avisa.
Apagar preço de modelo em uso é o tipo de limpeza que derruba produção.
"""

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.models.models import ModelPricing  # noqa: E402

ARQUIVO = Path(__file__).resolve().parent / "dados" / "model_pricing.json"
CAMPOS = ("provider", "provider_type", "display_name", "input_per_million", "output_per_million", "status")


def carregar(arquivo: Path = ARQUIVO) -> list[dict]:
    modelos = json.loads(arquivo.read_text(encoding="utf-8"))
    vistos: set[str] = set()
    for m in modelos:
        faltando = {"model_id", *CAMPOS} - m.keys()
        if faltando:
            raise ValueError(f"{m.get('model_id', '?')}: faltam os campos {sorted(faltando)}")
        if m["model_id"] in vistos:
            raise ValueError(f"model_id repetido no seed: {m['model_id']}")
        vistos.add(m["model_id"])
        # Decimal a partir de TEXTO: preço em float perde centavos de milionésimo.
        m["input_per_million"] = Decimal(str(m["input_per_million"]))
        m["output_per_million"] = Decimal(str(m["output_per_million"]))
    return modelos


async def aplicar(db, modelos: list[dict], *, gravar: bool = True) -> dict[str, list[str]]:
    """Insere o que falta e atualiza o que divergiu. Devolve o que mudou."""
    existentes = {m.model_id: m for m in (await db.execute(select(ModelPricing))).scalars()}
    relatorio: dict[str, list[str]] = {"criados": [], "atualizados": [], "fora_do_seed": []}

    for dados in modelos:
        atual = existentes.get(dados["model_id"])
        if atual is None:
            relatorio["criados"].append(dados["model_id"])
            if gravar:
                db.add(ModelPricing(**dados))
            continue
        diferentes = [c for c in CAMPOS if getattr(atual, c) != dados[c]]
        if diferentes:
            relatorio["atualizados"].append(f"{dados['model_id']} ({', '.join(diferentes)})")
            if gravar:
                for campo in diferentes:
                    setattr(atual, campo, dados[campo])

    no_seed = {m["model_id"] for m in modelos}
    relatorio["fora_do_seed"] = sorted(set(existentes) - no_seed)
    if gravar:
        await db.commit()
    return relatorio


async def main(conferir: bool) -> int:
    modelos = carregar()
    if not modelos:
        print(f"[ERRO] {ARQUIVO} está vazio. Exporte de produção (ver o docstring).")
        return 1
    async with async_session_factory() as db:
        relatorio = await aplicar(db, modelos, gravar=not conferir)
    verbo = "seriam" if conferir else "foram"
    print(f"{len(relatorio['criados'])} {verbo} criados: {relatorio['criados']}")
    print(f"{len(relatorio['atualizados'])} {verbo} atualizados: {relatorio['atualizados']}")
    if relatorio["fora_do_seed"]:
        print(f"[AVISO] no banco e FORA do seed (não mexi): {relatorio['fora_do_seed']}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--conferir", action="store_true", help="mostra a diferença sem gravar")
    sys.exit(asyncio.run(main(parser.parse_args().conferir)))
