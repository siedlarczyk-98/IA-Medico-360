"""
Servidor que faz o papel de TODOS os serviços externos no teste de carga.

POR QUE EXISTE
O teste de carga local (etapa A de `scripts/carga/LEIAME.md`) quer medir o teto
do NOSSO lado — pool de conexões, workers, Redis, fila do DLP, pools HTTP — sem
pagar LLM e sem depender da Waid. O `sitecustomize.py` desta pasta redireciona
toda chamada httpx do backend para cá, com o host original no cabeçalho
`x-host-original`. Este servidor responde no formato de cada provedor, com a
LATÊNCIA medida em produção, porque é a latência que prende conexão e stream.

LATÊNCIAS (produção, 90 dias até 2026-09-08 — `medico360-latencia-orquestrador`)
    CLINICAL_REASONING / EXAM_REVIEW (claude-sonnet-5)  p50 32,8 s  p95 56,7 s
    QUICK_SEARCH (sonar-pro)                             p50 13,3 s  p95 28,5 s
    auxiliares no gpt-5.4-nano                           ~400-900 ms
    embeddings                                           ~150-400 ms
Tudo multiplicado por FALSO_ESCALA (padrão 1.0); a Waid, também por FALSO_ESCALA_WAID. Para injetar falha de provedor,
FALSO_ERRO_PCT (0-100) devolve 429 nessa fração das chamadas aos modelos.

Uso:
    python -m uvicorn falso_externo:app --app-dir scripts/carga --host 0.0.0.0 --port 9000
"""

import asyncio
import hashlib
import json
import math
import os
import random
import re
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

ESCALA = float(os.environ.get("FALSO_ESCALA", "1.0"))
ERRO_PCT = float(os.environ.get("FALSO_ERRO_PCT", "0"))
# Só a Waid (validate e members/by): para simular a Waid lenta no evento sem
# mexer na latência dos modelos.
ESCALA_WAID = float(os.environ.get("FALSO_ESCALA_WAID", "1.0"))

# Contadores expostos em /_estatisticas — para conferir, depois da rodada, que o
# backend chamou o que se esperava (e que nada escapou para a internet).
_contagem: dict[str, int] = {}
_abertos = {"streams": 0, "pico_streams": 0}


def _conta(chave: str) -> None:
    _contagem[chave] = _contagem.get(chave, 0) + 1


def _lognormal(p50: float, p95: float) -> float:
    """Sorteia uma duração com a mediana e o p95 dados (segundos)."""
    sigma = math.log(p95 / p50) / 1.645
    return random.lognormvariate(math.log(p50), sigma) * ESCALA


async def _espera(p50: float, p95: float) -> None:
    await asyncio.sleep(_lognormal(p50, p95))


# ── Perfis dos modelos que respondem ao médico ───────────────────────────────
# (p50 total, p95 total, p50 do primeiro token, caracteres da resposta)
_PERFIS = {
    "claude-sonnet-5": (32.8, 56.7, 3.0, 3200),
    "sonar-pro": (13.3, 28.5, 2.0, 1800),
    "gpt-5.4-nano": (8.0, 20.0, 1.0, 1500),
    "gpt-4o": (15.0, 30.0, 1.5, 2000),
    "gemini-2.5-flash": (8.0, 18.0, 1.0, 1800),
    "sabia-4-thinking": (25.0, 50.0, 5.0, 2000),
}
_PERFIL_PADRAO = (10.0, 25.0, 1.5, 1500)

_TEXTO_BASE = (
    "Resumo prático para o caso descrito. Segundo a 2022 AHA/ACC/HFSA Heart Failure "
    "Guideline e a Diretriz Brasileira de Insuficiência Cardíaca 2018, o tratamento "
    "inicial inclui enalapril, carvedilol e espironolactona, com ajuste pela função "
    "renal e pelo potássio. Em pacientes com fração de ejeção reduzida, considerar "
    "dapagliflozina. Monitorar pressão arterial, creatinina e sinais de congestão. "
    "Reavaliar em duas a quatro semanas e titular as doses conforme tolerância. "
)


def _texto(n_chars: int) -> str:
    return (_TEXTO_BASE * (n_chars // len(_TEXTO_BASE) + 1))[:n_chars]


def _pedacos(texto: str, tamanho: int = 24) -> list[str]:
    return [texto[i:i + tamanho] for i in range(0, len(texto), tamanho)]


async def _cronograma(modelo: str):
    """Gera (atraso, pedaço) respeitando primeiro token e duração total do perfil."""
    p50, p95, ttft50, n_chars = _PERFIS.get(modelo, _PERFIL_PADRAO)
    total = _lognormal(p50, p95)
    ttft = min(_lognormal(ttft50, ttft50 * 2.5), total * 0.6)
    pedacos = _pedacos(_texto(n_chars))
    intervalo = max(total - ttft, 0.1) / max(len(pedacos), 1)
    await asyncio.sleep(ttft)
    for i, p in enumerate(pedacos):
        if i:
            await asyncio.sleep(intervalo)
        yield p


def _falha_injetada() -> Response | None:
    if ERRO_PCT and random.uniform(0, 100) < ERRO_PCT:
        _conta("erro_injetado_429")
        return JSONResponse({"error": {"type": "rate_limit_error", "message": "falso"}}, status_code=429)
    return None


def _stream_sse(gerador) -> StreamingResponse:
    async def envolve():
        _abertos["streams"] += 1
        _abertos["pico_streams"] = max(_abertos["pico_streams"], _abertos["streams"])
        try:
            async for linha in gerador:
                yield linha
        finally:
            _abertos["streams"] -= 1

    return StreamingResponse(envolve(), media_type="text/event-stream")


# ── Anthropic ────────────────────────────────────────────────────────────────

async def anthropic_messages(req: Request, corpo: dict) -> Response:
    modelo = corpo.get("model", "")
    _conta(f"anthropic:{modelo}:{'stream' if corpo.get('stream') else 'complete'}")
    if (falha := _falha_injetada()) is not None:
        return falha

    if not corpo.get("stream"):
        # Limpeza de bula e descrição de imagem pelo Haiku: curto, sem stream.
        await _espera(2.0, 5.0)
        return JSONResponse({
            "content": [{"type": "text", "text": _texto(900)}],
            "usage": {"input_tokens": 1200, "output_tokens": 250},
        })

    async def eventos():
        def ev(d: dict) -> str:
            return f"event: {d['type']}\ndata: {json.dumps(d)}\n\n"

        yield ev({"type": "message_start", "message": {"usage": {"input_tokens": 1500}}})
        yield ev({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
        n = 0
        async for pedaco in _cronograma(modelo):
            n += len(pedaco)
            yield ev({"type": "content_block_delta", "index": 0,
                      "delta": {"type": "text_delta", "text": pedaco}})
        yield ev({"type": "content_block_stop", "index": 0})
        yield ev({"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                  "usage": {"output_tokens": n // 4}})
        yield ev({"type": "message_stop"})

    return _stream_sse(eventos())


# ── OpenAI / Perplexity / Maritaca (chat completions) ────────────────────────

def _json_auxiliar(mensagens: list[dict]) -> str | None:
    """Reconhece as chamadas auxiliares pelo prompt e devolve o JSON que o código espera."""
    texto = " ".join(
        m["content"] if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
        for m in mensagens
    )
    usuario = next(
        (m["content"] for m in reversed(mensagens)
         if m.get("role") == "user" and isinstance(m.get("content"), str)),
        "",
    )
    baixo = usuario.lower()

    if "sistema de triagem da plataforma" in texto:
        # O template inteiro vem na mensagem do usuário; a pergunta é o que
        # segue o último "Pergunta:". Sem este corte, as palavras do próprio
        # template ("bula", "receita") decidiriam o modo.
        baixo = usuario.rsplit("Pergunta:", 1)[-1].lower()
        if "bula" in baixo:
            return json.dumps({"mode": "PHARMA_BULA", "confidence": 0.95})
        if "receita" in baixo:
            return json.dumps({"mode": "PHARMA_RECEITA", "confidence": 0.95})
        if "genérico" in baixo or "generico" in baixo:
            return json.dumps({"mode": "PHARMA_GENERICO", "confidence": 0.95})
        if "interação" in baixo or "interacao" in baixo or " com " in baixo:
            return json.dumps({"mode": "PHARMA_CHECK", "confidence": 0.95})
        return json.dumps({"mode": "QUICK_SEARCH", "confidence": 0.9})
    if "medical query classifier and normalizer" in texto:
        return json.dumps({"cacheable": True, "normalized_prompt": usuario[:300]})
    if "avalia se uma pergunta precisa de informações adicionais" in texto:
        return json.dumps({"sufficient": True, "questions": []})
    if "retorne APENAS um JSON com dois campos" in texto:
        return json.dumps({"specialty": "Cardiologia", "topic": "insuficiência cardíaca"})
    if "Extraia TODOS os medicamentos" in texto:
        if "[PROMPT]" in texto:
            return json.dumps([
                {"raw": "enalapril", "normalized": "enalapril", "source": "response"},
                {"raw": "carvedilol", "normalized": "carvedilol", "source": "response"},
            ])
        pergunta = usuario.rsplit("Texto:", 1)[-1].lower()
        achados = [m for m in ("losartana", "amiodarona", "varfarina", "dipirona", "enalapril")
                   if m in pergunta] or ["dipirona"]
        return json.dumps([{"raw": m, "normalized": m} for m in achados])
    if "Extract all references cited" in texto:
        return json.dumps(["2022 AHA/ACC/HFSA Heart Failure Guideline",
                           "Diretriz Brasileira de Insuficiência Cardíaca 2018"])
    return None


async def chat_completions(req: Request, corpo: dict, host: str) -> Response:
    modelo = corpo.get("model", "")
    mensagens = corpo.get("messages", [])
    stream = bool(corpo.get("stream"))
    _conta(f"{host}:{modelo}:{'stream' if stream else 'complete'}")

    if not stream:
        aux = _json_auxiliar(mensagens)
        if aux is not None:
            await _espera(0.55, 1.2)
            conteudo = aux
        else:
            if (falha := _falha_injetada()) is not None:
                return falha
            p50, p95, _, n = _PERFIS.get(modelo, _PERFIL_PADRAO)
            await _espera(p50, p95)
            conteudo = _texto(n)
        return JSONResponse({
            "choices": [{"message": {"role": "assistant", "content": conteudo}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 400, "completion_tokens": max(len(conteudo) // 4, 1)},
        })

    if (falha := _falha_injetada()) is not None:
        return falha

    perplexity = "perplexity" in host

    async def eventos():
        n = 0
        i = 0
        async for pedaco in _cronograma(modelo):
            n += len(pedaco)
            ev: dict = {"choices": [{"index": 0, "delta": {"content": pedaco}}]}
            if perplexity and i == 3:
                ev["search_results"] = [
                    {"title": "Heart failure guideline", "url": "https://pubmed.ncbi.nlm.nih.gov/35363499/"},
                    {"title": "Diretriz IC", "url": "https://www.scielo.br/j/abc/a/xyz"},
                ]
            i += 1
            yield f"data: {json.dumps(ev)}\n\n"
        yield "data: " + json.dumps({
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 900, "completion_tokens": n // 4},
        }) + "\n\n"
        yield "data: [DONE]\n\n"

    return _stream_sse(eventos())


async def openai_embeddings(req: Request, corpo: dict) -> Response:
    _conta("openai:embeddings")
    await _espera(0.25, 0.5)
    entradas = corpo.get("input", "")
    if isinstance(entradas, str):
        entradas = [entradas]
    dados = []
    for i, t in enumerate(entradas):
        # Determinístico por texto: a mesma pergunta dá o mesmo vetor, então o
        # cache semântico acerta como acertaria em produção.
        semente = int(hashlib.sha256(str(t).encode()).hexdigest()[:8], 16)
        rnd = random.Random(semente)
        v = [rnd.uniform(-1, 1) for _ in range(1536)]
        norma = math.sqrt(sum(x * x for x in v))
        dados.append({"index": i, "embedding": [x / norma for x in v]})
    return JSONResponse({"data": dados, "usage": {"prompt_tokens": 20}})


async def openai_responses(req: Request, corpo: dict) -> Response:
    _conta(f"openai:responses:{corpo.get('model')}")
    await _espera(10.0, 25.0)
    return JSONResponse({
        "output": [{"type": "message", "content": [{"type": "output_text", "text": _texto(1500), "annotations": []}]}],
        "usage": {"input_tokens": 800, "output_tokens": 400},
    })


async def gemini(req: Request, corpo: dict) -> Response:
    caminho = req.url.path
    modelo = caminho.split("/models/")[-1].split(":")[0]
    _conta(f"gemini:{modelo}")
    if ":streamGenerateContent" in caminho:
        async def eventos():
            async for pedaco in _cronograma(modelo):
                yield "data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": pedaco}]}}]}) + "\n\n"
            yield "data: " + json.dumps({
                "candidates": [{"content": {"parts": []}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 800, "candidatesTokenCount": 400},
            }) + "\n\n"
        return _stream_sse(eventos())
    p50, p95, _, n = _PERFIS.get(modelo, _PERFIL_PADRAO)
    await _espera(p50, p95)
    return JSONResponse({
        "candidates": [{"content": {"parts": [{"text": _texto(n)}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 800, "candidatesTokenCount": 400},
    })


# ── PubMed (eutils) ──────────────────────────────────────────────────────────

async def eutils(req: Request) -> Response:
    caminho = req.url.path
    if caminho.endswith("esearch.fcgi"):
        _conta("pubmed:esearch")
        await _espera(0.3, 0.8)
        ids = [str(30000000 + random.randint(0, 9999999)) for _ in range(random.choice([0, 1, 1, 2]))]
        return JSONResponse({"esearchresult": {"count": str(len(ids)), "idlist": ids}})
    if caminho.endswith("efetch.fcgi"):
        _conta("pubmed:efetch")
        await _espera(0.4, 1.0)
        ids = (req.query_params.get("id") or "").split(",")
        artigos = "".join(
            f"<PubmedArticle><PMID Version=\"1\">{i}</PMID><ArticleTitle>Guideline update {i}"
            f"</ArticleTitle><AbstractText>Resumo sintético.</AbstractText></PubmedArticle>"
            for i in ids if i
        )
        return Response(f"<PubmedArticleSet>{artigos}</PubmedArticleSet>", media_type="text/xml")
    _conta(f"pubmed:{caminho}")
    return JSONResponse({})


# ── PharmaDB ─────────────────────────────────────────────────────────────────

def _id_de(nome: str) -> int:
    return int(hashlib.md5(nome.lower().encode()).hexdigest()[:6], 16)


async def pharmadb(req: Request) -> Response:
    caminho = req.url.path
    _conta("pharmadb:" + re.sub(r"/\d+", "/{id}", caminho))
    await _espera(0.25, 0.7)
    q = req.query_params.get("q", "dipirona")
    if caminho == "/auth/token":
        return JSONResponse({"access_token": "falso", "token_type": "bearer", "expires_in": 3600})
    if caminho.startswith("/v1/principios-ativos/busca"):
        return JSONResponse({"items": [{"id": _id_de(q), "nome_dcb": q.lower()}]})
    if re.fullmatch(r"/v1/principios-ativos/\d+", caminho):
        pa = int(caminho.rsplit("/", 1)[1])
        return JSONResponse({"id": pa, "nome_dcb": f"pa-{pa}", "codigo_atc": "C09AA02", "total_interacoes": 12})
    if caminho.startswith("/v1/interacoes/pa/"):
        pa = int(caminho.rsplit("/", 1)[1])
        return JSONResponse({"interacoes": [{
            "pa_a": {"id": pa, "nome_dcb": f"pa-{pa}"},
            "pa_b": {"id": pa + 1, "nome_dcb": f"pa-{pa + 1}"},
            "gravidade": "moderada", "tipo_interacao": "farmacodinâmica",
            "efeito_clinico": "Aumento do risco de hipercalemia.",
            "mecanismo": "Efeito aditivo.", "manejo_clinico": "Monitorar potássio.",
            "referencias": [],
        }]})
    if caminho.startswith("/v1/bulas/busca"):
        return JSONResponse({"items": [{"id": _id_de(q), "tipo": "profissional"}]})
    if re.fullmatch(r"/v1/bulas/\d+", caminho):
        return JSONResponse({
            "id": int(caminho.rsplit("/", 1)[1]), "tipo": "profissional",
            "produto": {"nome": q, "laboratorio": "Lab Falso", "principios_ativos": [q]},
            "texto_indicacoes": _texto(600), "texto_contraindicacoes": _texto(400),
            "texto_posologia": _texto(500), "texto_reacoes_adversas": _texto(500),
            "texto_interacoes": _texto(400),
        })
    if caminho.startswith("/v1/produtos/busca"):
        return JSONResponse({"items": [{
            "id": _id_de(q), "nome": q.title(), "laboratorio": "Lab Falso", "tarja": "vermelha",
            "categoria_regulatoria": "Genérico", "principios_ativos": [q],
        }]})
    if caminho.endswith("/receita"):
        return JSONResponse({"produto_nome": q, "tarja": "vermelha", "tipo": "simples",
                             "cor_receita": "branca", "requer_receita": True, "retencao": False,
                             "vias": 1, "validade_dias": 30})
    if caminho.endswith("/genericos"):
        return JSONResponse({"items": [{"id": 1, "nome": "Genérico A", "laboratorio": "Lab A"},
                                       {"id": 2, "nome": "Genérico B", "laboratorio": "Lab B"}]})
    if caminho.endswith("/historico-comercializacao"):
        return JSONResponse({"items": []})
    return JSONResponse({"items": []})


# ── Curseduca / Waid ─────────────────────────────────────────────────────────

_ESPECIALIDADES = ["Cardiologia", "Clínica Médica", "Pediatria", "Ginecologia e Obstetrícia",
                   "Medicina de Família e Comunidade", "GENERALISTA"]


async def curseduca(req: Request, corpo: dict | None) -> Response:
    caminho = req.url.path
    if caminho.endswith("/embed-identity-tokens/validate"):
        _conta("waid:validate")
        await asyncio.sleep(_lognormal(0.35, 1.0) * ESCALA_WAID)
        token = (corpo or {}).get("token", "")
        # Token do gerador: "carga-<n>-<qualquer coisa>". O resto é recusado,
        # como a Waid recusaria.
        m = re.match(r"carga-(\d+)-", token)
        if not m:
            return JSONResponse({"message": "invalid"}, status_code=400)
        n = int(m.group(1))
        return JSONResponse({"uuid": f"carga-{n:05d}", "email": f"carga{n:05d}@carga.invalid",
                             "name": f"Médico Carga {n}"})
    if caminho.endswith("/members/by"):
        _conta("waid:members_by")
        await asyncio.sleep(_lognormal(0.35, 1.0) * ESCALA_WAID)
        email = req.query_params.get("email", "")
        m = re.match(r"carga(\d+)@", email)
        n = int(m.group(1)) if m else 0
        return JSONResponse({
            "id": n, "email": email, "name": f"Médico Carga {n}",
            "groups": [{"id": 1, "name": f"[CFM] {_ESPECIALIDADES[n % len(_ESPECIALIDADES)]}"}],
        })
    _conta(f"waid:{caminho}")
    return JSONResponse({})


# ── Roteamento pelo host original ────────────────────────────────────────────

async def qualquer(req: Request) -> Response:
    host = req.headers.get("x-host-original", "")
    corpo: dict | None = None
    if req.method == "POST":
        bruto = await req.body()
        try:
            corpo = json.loads(bruto) if bruto else {}
        except ValueError:
            corpo = {}

    if host == "api.anthropic.com":
        return await anthropic_messages(req, corpo or {})
    if host in ("api.openai.com", "api.perplexity.ai", "chat.maritaca.ai"):
        caminho = req.url.path
        if caminho.endswith("/embeddings"):
            return await openai_embeddings(req, corpo or {})
        if caminho.endswith("/responses"):
            return await openai_responses(req, corpo or {})
        return await chat_completions(req, corpo or {}, host)
    if host == "generativelanguage.googleapis.com":
        return await gemini(req, corpo or {})
    if host == "eutils.ncbi.nlm.nih.gov":
        return await eutils(req)
    if host == "api.pharmadb.com.br":
        return await pharmadb(req)
    if "curseduca" in host:
        return await curseduca(req, corpo)
    if host == "api.sendgrid.com":
        _conta("sendgrid")
        return Response(status_code=202)

    _conta(f"desconhecido:{host}{req.url.path}")
    return JSONResponse({})


async def estatisticas(req: Request) -> Response:
    return JSONResponse({"chamadas": dict(sorted(_contagem.items())), **_abertos,
                         "escala": ESCALA, "escala_waid": ESCALA_WAID, "erro_pct": ERRO_PCT, "agora": time.time()})


async def zerar(req: Request) -> Response:
    _contagem.clear()
    _abertos["pico_streams"] = _abertos["streams"]
    return PlainTextResponse("ok")


app = Starlette(routes=[
    Route("/_estatisticas", estatisticas),
    Route("/_zerar", zerar, methods=["POST"]),
    Route("/{caminho:path}", qualquer, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
])
