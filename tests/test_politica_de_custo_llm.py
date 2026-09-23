"""
Política de custo de LLM — toda rota que gasta precisa contabilizar.

POR QUE ESTE ARQUIVO EXISTE
Metade dos achados da revisão externa de 2026-09-11 tinha a mesma origem: uma
invariante respeitada no caminho principal que um módulo mais novo não herdou.
Custo de LLM foi o caso mais claro — `record_cost` faltou primeiro no `/query`,
foi corrigido, e depois faltou de novo em `/calculators/{slug}/extract` e no
redator de notícias.

POR QUE NÃO BASTA O TESTE QUE JÁ EXISTIA
`test_orquestrador_paridade.test_todo_produtor_de_custo_registra` varre o
FONTE procurando `await calculate_cost(` sem `record_cost`. Isso só enxerga
arquivo que JÁ calcula custo. `news_writer_service.py` chamava a API da
Anthropic e nunca chamava `calculate_cost` — passou despercebido por meses, e o
teste seguia verde.

A lição: ancorar em ROTA, não em texto de arquivo. É o mesmo mecanismo de
`tests/test_authorization.py`, que enumera o OpenAPI e exige decisão explícita.

AS TRÊS POLÍTICAS
`DESCONTA`  - gasta LLM com um médico na frente; chama `check_limit` antes e
              `record_cost` depois. O teto semanal do `beta_user` depende disso.
`REGISTRA`  - gasta LLM sem titular a quem cobrar (pipeline agendado, chamada
              interna). Apura o custo e o registra, mas não mexe no medidor.
              Ver T3 em `docs/plano-correcoes.md`.
`NAO_GASTA` - não chama modelo nenhum.
"""

import ast
import pathlib

import pytest

from app.main import app

RAIZ_APP = pathlib.Path(__file__).resolve().parents[1] / "app"

DESCONTA = "desconta_do_medidor"
REGISTRA = "registra_sem_titular"
NAO_GASTA = "nao_gasta_llm"

# Declare toda rota nova aqui. `test_toda_rota_declara_politica_de_custo` falha
# enquanto isso não for feito — é a trava contra o esquecimento, não contra o
# erro de hoje.
POLITICA_DE_CUSTO: dict[tuple[str, str], str] = {
    # ── Gastam LLM com o médico na frente ────────────────────────────────
    ("POST", "/api/v1/orquestrador/query"): DESCONTA,
    ("POST", "/api/v1/orquestrador/stream"): DESCONTA,
    ("POST", "/api/v1/agregador/stream"): DESCONTA,
    # Caminho de imagem chama o Haiku para descrever o anexo.
    ("POST", "/api/v1/uploads/extract"): DESCONTA,
    # Extração de campos de calculadora via `gpt-5.4-mini`. Era a rota que
    # gastava fora do medidor — corrigida na Fase 1.
    ("POST", "/api/v1/calculators/{slug}/extract"): DESCONTA,
    # ── Gastam LLM sem titular ───────────────────────────────────────────
    # Dispara coleta + tagging + redação. O mesmo pipeline roda pelo agendador
    # noturno, sem usuário no escopo: não há a quem descontar. O custo é apurado
    # e devolvido em `custo_usd`.
    ("POST", "/api/v1/news/admin/pipeline"): REGISTRA,
    # ── Não chamam modelo ────────────────────────────────────────────────
    ("DELETE", "/api/v1/auth/me"): NAO_GASTA,
    ("DELETE", "/api/v1/calculators/{slug}/favorite"): NAO_GASTA,
    ("DELETE", "/api/v1/folders/{folder_id}"): NAO_GASTA,
    ("DELETE", "/api/v1/news/me/keywords/{termo}"): NAO_GASTA,
    ("GET", "/api/v1/agregador/models"): NAO_GASTA,
    ("GET", "/api/v1/auth/me"): NAO_GASTA,
    ("GET", "/api/v1/auth/me/consentimentos"): NAO_GASTA,
    ("GET", "/api/v1/auth/me/export"): NAO_GASTA,
    ("GET", "/api/v1/calculators"): NAO_GASTA,
    ("GET", "/api/v1/calculators/{slug}"): NAO_GASTA,
    ("GET", "/api/v1/calculators/{slug}/history"): NAO_GASTA,
    ("GET", "/api/v1/conversations"): NAO_GASTA,
    ("GET", "/api/v1/conversations/{conversation_id}"): NAO_GASTA,
    ("GET", "/api/v1/dea/locais"): NAO_GASTA,
    ("GET", "/api/v1/folders"): NAO_GASTA,
    ("GET", "/api/v1/health"): NAO_GASTA,
    ("GET", "/api/v1/health/ready"): NAO_GASTA,
    ("GET", "/api/v1/landing-pages/{slug}/check"): NAO_GASTA,
    ("GET", "/api/v1/meta/especialidades"): NAO_GASTA,
    ("GET", "/api/v1/news/articles/{article_id}"): NAO_GASTA,
    ("GET", "/api/v1/news/favorites"): NAO_GASTA,
    ("GET", "/api/v1/news/highlights"): NAO_GASTA,
    # Prévia de palavra-chave: casa termos contra artigos já coletados, sem LLM.
    ("GET", "/api/v1/news/keywords/preview"): NAO_GASTA,
    ("GET", "/api/v1/news/me/keywords"): NAO_GASTA,
    ("GET", "/api/v1/news/me/preferences"): NAO_GASTA,
    ("GET", "/api/v1/news/me/topics"): NAO_GASTA,
    ("GET", "/api/v1/users/usage"): NAO_GASTA,
    ("PATCH", "/api/v1/auth/admin/users/{user_id}/especialidade"): NAO_GASTA,
    ("PATCH", "/api/v1/auth/me"): NAO_GASTA,
    ("PATCH", "/api/v1/folders/conversations/bulk"): NAO_GASTA,
    ("PATCH", "/api/v1/folders/conversations/{conversation_id}/folder"): NAO_GASTA,
    ("POST", "/api/v1/auth/embed/identidade"): NAO_GASTA,
    ("POST", "/api/v1/auth/embed/token"): NAO_GASTA,
    ("POST", "/api/v1/auth/invite/accept"): NAO_GASTA,
    ("POST", "/api/v1/auth/logout"): NAO_GASTA,
    ("POST", "/api/v1/auth/invite/generate"): NAO_GASTA,
    ("POST", "/api/v1/auth/me/consentimentos/{tipo}/revogar"): NAO_GASTA,
    ("POST", "/api/v1/auth/onboarding"): NAO_GASTA,
    ("POST", "/api/v1/auth/otp/request"): NAO_GASTA,
    ("POST", "/api/v1/auth/otp/verify"): NAO_GASTA,
    ("POST", "/api/v1/auth/register"): NAO_GASTA,
    ("POST", "/api/v1/auth/session/renew"): NAO_GASTA,
    # A calculadora em si é fórmula determinística — o LLM só entra no
    # `/extract`, que pré-preenche os campos.
    ("POST", "/api/v1/calculators/{slug}/execute"): NAO_GASTA,
    ("POST", "/api/v1/dea/dispositivos/{dispositivo_id}/verificacoes"): NAO_GASTA,
    ("POST", "/api/v1/dea/locais"): NAO_GASTA,
    ("POST", "/api/v1/folders"): NAO_GASTA,
    ("POST", "/api/v1/landing-pages/accounting/submit"): NAO_GASTA,
    ("POST", "/api/v1/landing-pages/calculators/submit"): NAO_GASTA,
    ("POST", "/api/v1/landing-pages/finance/submit"): NAO_GASTA,
    ("POST", "/api/v1/landing-pages/partners/submit"): NAO_GASTA,
    ("POST", "/api/v1/news/favorites/toggle"): NAO_GASTA,
    ("POST", "/api/v1/news/feedback/nao-interessa"): NAO_GASTA,
    ("POST", "/api/v1/news/me/keywords"): NAO_GASTA,
    ("POST", "/api/v1/prevent/calculate"): NAO_GASTA,
    ("PUT", "/api/v1/calculators/{slug}/favorite"): NAO_GASTA,
    ("PUT", "/api/v1/folders/{folder_id}"): NAO_GASTA,
    ("PUT", "/api/v1/news/me/preferences"): NAO_GASTA,
    ("PUT", "/api/v1/news/me/topics"): NAO_GASTA,
}


def _rotas_da_app() -> list[tuple[str, str]]:
    schema = app.openapi()
    rotas = sorted(
        (metodo.upper(), caminho)
        for caminho, operacoes in schema["paths"].items()
        for metodo in operacoes
        if metodo.upper() not in {"HEAD", "OPTIONS"}
    )
    assert rotas, "Nenhuma rota encontrada — a varredura quebrou, não a aplicação."
    return rotas


def _rotas_com_politica(*politicas: str) -> list[tuple[str, str]]:
    return [r for r, p in POLITICA_DE_CUSTO.items() if p in politicas]


# ── As travas bidirecionais ──────────────────────────────────────────────


def test_toda_rota_declara_politica_de_custo():
    """
    Rota nova precisa de decisão explícita sobre custo.

    Sem isto, uma rota que chama modelo entra em produção gastando fora do
    medidor — exatamente o que aconteceu com a calculadora e com o redator de
    notícias, cada um por um caminho diferente.
    """
    sem_politica = [r for r in _rotas_da_app() if r not in POLITICA_DE_CUSTO]
    assert not sem_politica, (
        "Rota(s) sem política de custo declarada:\n  "
        + "\n  ".join(f"{m} {p}" for m, p in sem_politica)
        + "\n\nDeclare como DESCONTA, REGISTRA ou NAO_GASTA em "
        "tests/test_politica_de_custo_llm.py.\n"
        "Se a rota chama modelo, ela precisa de `check_limit` + `record_cost` "
        "(DESCONTA) ou de `calculate_cost` com registro (REGISTRA)."
    )


def test_politica_nao_referencia_rota_inexistente():
    """Rota removida deve sair do mapa, senão ele vira ficção."""
    existentes = set(_rotas_da_app())
    fantasmas = [r for r in POLITICA_DE_CUSTO if r not in existentes]
    assert not fantasmas, f"POLITICA_DE_CUSTO tem rotas que não existem mais: {fantasmas}"


# ── A verificação de comportamento ───────────────────────────────────────
#
# As travas acima garantem que alguém DECIDIU. Estas garantem que a decisão foi
# implementada: procuram as chamadas no grafo de código alcançável a partir do
# handler, e não por texto solto no arquivo.


def _modulo_de(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))


def _chamadas_no_arquivo(caminho: pathlib.Path) -> set[str]:
    """Nomes de função chamados no arquivo (`f()` e `obj.f()`)."""
    nomes: set[str] = set()
    for no in ast.walk(_modulo_de(caminho)):
        if isinstance(no, ast.Call):
            alvo = no.func
            if isinstance(alvo, ast.Name):
                nomes.add(alvo.id)
            elif isinstance(alvo, ast.Attribute):
                nomes.add(alvo.attr)
    return nomes


# Onde mora o código de cada rota que gasta. Uma rota costuma delegar ao
# service, então o par (router, service) é o que precisa ser inspecionado.
# NOTA: `check_limit` costuma ficar no ENDPOINT (é gate de entrada, antes de
# gastar) e `record_cost` no SERVICE (é consequência, depois de apurar). Por isso
# o par precisa ser inspecionado junto — olhar só o service acusaria falsamente
# as quatro rotas do orquestrador e do agregador.
ARQUIVOS_POR_ROTA: dict[tuple[str, str], tuple[str, ...]] = {
    ("POST", "/api/v1/orquestrador/query"): (
        "api/v1/endpoints/orquestrador.py",
        "services/orquestrador_service.py",
    ),
    ("POST", "/api/v1/orquestrador/stream"): (
        "api/v1/endpoints/orquestrador.py",
        "services/orquestrador_stream_service.py",
    ),
    ("POST", "/api/v1/agregador/stream"): (
        "api/v1/endpoints/agregador.py",
        "services/agregador_service.py",
    ),
    ("POST", "/api/v1/uploads/extract"): ("api/v1/endpoints/uploads.py",),
    ("POST", "/api/v1/calculators/{slug}/extract"): (
        "calculators/routers/calculators_router.py",
        "calculators/services/extraction_service.py",
    ),
    ("POST", "/api/v1/news/admin/pipeline"): ("services/news_writer_service.py",),
}


@pytest.mark.parametrize(("metodo", "caminho"), _rotas_com_politica(DESCONTA))
def test_rota_que_desconta_chama_check_limit_e_record_cost(metodo, caminho):
    """
    `check_limit` sem `record_cost` é um teto que nunca é atingido: o medidor
    é lido mas nunca alimentado. Foi assim que o `/query` passou meses deixando
    o `beta_user` gastar sem limite.
    """
    arquivos = ARQUIVOS_POR_ROTA[(metodo, caminho)]
    chamadas: set[str] = set()
    for relativo in arquivos:
        chamadas |= _chamadas_no_arquivo(RAIZ_APP / relativo)

    faltando = {"check_limit", "record_cost"} - chamadas
    assert not faltando, (
        f"{metodo} {caminho} está declarada como DESCONTA mas não chama "
        f"{sorted(faltando)} em {list(arquivos)}."
    )


@pytest.mark.parametrize(("metodo", "caminho"), _rotas_com_politica(REGISTRA))
def test_rota_que_registra_apura_o_custo(metodo, caminho):
    """
    Sem titular não há `record_cost` — mas o custo tem de ser APURADO, senão o
    gasto fica invisível para qualquer relatório. Era o caso do redator: rodava
    `claude-sonnet-5` e nunca chamava `calculate_cost`.
    """
    arquivos = ARQUIVOS_POR_ROTA[(metodo, caminho)]
    chamadas: set[str] = set()
    for relativo in arquivos:
        chamadas |= _chamadas_no_arquivo(RAIZ_APP / relativo)

    assert "calculate_cost" in chamadas, (
        f"{metodo} {caminho} está declarada como REGISTRA mas não chama "
        f"`calculate_cost` em {list(arquivos)} — o gasto fica invisível."
    )


def test_mapa_de_arquivos_cobre_toda_rota_que_gasta():
    """O mapa acima não pode ficar para trás do dicionário de políticas."""
    que_gastam = set(_rotas_com_politica(DESCONTA, REGISTRA))
    sem_mapa = que_gastam - set(ARQUIVOS_POR_ROTA)
    assert not sem_mapa, (
        f"Rotas declaradas como gastadoras mas ausentes de ARQUIVOS_POR_ROTA: {sem_mapa}"
    )

    for rota, arquivos in ARQUIVOS_POR_ROTA.items():
        for relativo in arquivos:
            assert (RAIZ_APP / relativo).exists(), (
                f"ARQUIVOS_POR_ROTA aponta para arquivo inexistente em {rota}: {relativo}"
            )


# ── O modelo tem de ter preço ────────────────────────────────────────────


def test_todo_model_id_do_codigo_tem_pricing_declarado():
    """
    `calculate_cost` devolve `Decimal("0")` em silêncio para modelo sem linha em
    `model_pricing` (ver `pricing.get_model_pricing`). Então contabilizar um
    modelo não cadastrado é o pior dos mundos: parece contabilizado e vale zero.

    Este teste não consulta o banco — ele trava a lista de modelos que o código
    usa, para que acrescentar um obrigue a decidir sobre o preço. Quando um
    modelo entra aqui, o `scripts/add_*.py` correspondente precisa existir.
    """
    modelos_conhecidos = {
        # clínicos e auxiliares
        # `claude-sonnet-5` atende CLINICAL_REASONING e EXAM_REVIEW desde a
        # migração de 2026-09-15; o 4-6 segue referenciado em `context_budget`.
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "gpt-5.4-nano",
        "gpt-5.4-mini",
        "gpt-5",
        "gpt-4o",
        "gemini-2.5-flash",
        "sonar-pro",
        "sabia-4",
        "sabia-4-thinking",
        # legado, ainda referenciado em context_budget
        "claude-sonnet-4-20250514",
    }

    encontrados: set[str] = set()
    for arquivo in RAIZ_APP.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        for modelo in modelos_conhecidos:
            if f'"{modelo}"' in texto:
                encontrados.add(modelo)

    # Um ID com sufixo de data indica que o canônico e o datado divergiram —
    # e divergência entre o payload e o `calculate_cost` vira custo zero.
    datados = set()
    for arquivo in RAIZ_APP.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        for linha in texto.splitlines():
            if "claude-haiku-4-5-2" in linha or "claude-sonnet-4-6-2" in linha:
                datados.add(f"{arquivo.relative_to(RAIZ_APP)}: {linha.strip()[:80]}")

    assert not datados, (
        "ID de modelo com sufixo de data no código. Use o ID canônico — um "
        "literal datado que diverge do usado em `calculate_cost` faz o custo "
        "virar zero em silêncio:\n  " + "\n  ".join(sorted(datados))
    )
