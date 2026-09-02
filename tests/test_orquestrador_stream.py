"""
Streaming do Orquestrador — contrato SSE (item 1.3 do plano de prontidão).

O front-end depende da ORDEM e do NOME dos eventos. Uma mudança silenciosa aqui
quebra a interface sem quebrar nenhum teste — até agora.

Contrato exercitado:
  start → token* → text_done → done   (fluxo normal)
  start → token → done        (atalho de saudação, sem gastar chamada de modelo)
  error                       (falha fatal, sem stack trace vazando)

Os providers são fakes; nada toca a rede.
"""

import asyncio
import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.integracoes import ai_providers
from app.services.integracoes.ai_providers import StreamToken
from app.services.orquestrador_stream_service import OrquestradorStreamService


def parse_sse(bruto: list[str]) -> list[tuple[str, dict]]:
    """Converte os frames SSE crus em [(evento, dados)]."""
    eventos = []
    for frame in bruto:
        linhas = frame.strip().split("\n")
        nome = linhas[0].removeprefix("event: ")
        dados = json.loads(linhas[1].removeprefix("data: "))
        eventos.append((nome, dados))
    return eventos


class ProviderStreamFake:
    def __init__(self, pedacos=("Primeiro ", "segundo ", "terceiro.")):
        self.pedacos = pedacos

    async def complete(self, model_id, prompt, **kwargs):
        raise NotImplementedError

    async def stream(self, model_id, prompt, **kwargs):
        for p in self.pedacos:
            yield StreamToken(delta=p)
        yield StreamToken(delta="", done=True, tokens_in=100, tokens_out=50)


class ProviderStreamQueFalha:
    async def complete(self, model_id, prompt, **kwargs):
        raise RuntimeError("provedor indisponível")

    async def stream(self, model_id, prompt, **kwargs):
        raise RuntimeError("provedor indisponível")
        yield  # pragma: no cover — torna a função um gerador


@pytest.fixture
def servico(db, db_conn, user, monkeypatch):
    """
    Serviço apontado para a sessão do teste.

    O stream abre a própria sessão via `session_factory`, fora do `get_db`.
    Injetamos uma factory presa à mesma conexão do teste para que o rollback
    do harness continue valendo.
    """
    factory = async_sessionmaker(bind=db_conn, expire_on_commit=False)
    return OrquestradorStreamService(factory, user.id)


@pytest.fixture(autouse=True)
def sem_dependencias_externas(monkeypatch):
    """Desliga cache semântico, triagem remota e enriquecimento."""
    async def _sem_cache(*a, **k):
        return None

    async def _triagem(*a, **k):
        return {"mode": "QUICK_SEARCH", "confidence": 0.99, "category": "QUICK_SEARCH"}

    async def _sem_clarificacao(*a, **k):
        return {"sufficient": True, "questions": []}

    async def _sem_redis_get(*a, **k):
        return None

    async def _sem_redis_set(*a, **k):
        return None

    # Sem `raising=False`: se o nome mudar de novo, é melhor o teste quebrar do
    # que passar a não desligar nada silenciosamente — foi o que aconteceu
    # quando `_check_clarification` virou `check_clarification`.
    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.check_clarification",
        _sem_clarificacao,
    )
    # Sem isso cada teste paga o timeout de conexão do Redis, que não existe no CI.
    monkeypatch.setattr("app.services.cache_service.get_json", _sem_redis_get)
    monkeypatch.setattr("app.services.cache_service.set_json", _sem_redis_set)


async def _coleta(servico, **kwargs) -> list[tuple[str, dict]]:
    frames = [f async for f in servico.stream(**kwargs)]
    return parse_sse(frames)


# ── Atalho de saudação ───────────────────────────────────────────────────

async def test_saudacao_nao_gasta_chamada_de_modelo(servico, monkeypatch):
    """
    "Oi" não pode custar uma chamada de LLM. O atalho responde local.
    Se algum provider for chamado, a guarda de rede do harness derruba o teste.
    """
    eventos = await _coleta(servico, prompt="Oi")

    nomes = [e for e, _ in eventos]
    assert nomes == ["start", "token", "done"]
    assert eventos[0][1]["mode"] == "OFF_TOPIC"
    assert "Médico 360" in eventos[1][1]["text"]


# ── Fluxo normal ─────────────────────────────────────────────────────────

async def test_ordem_dos_eventos_no_fluxo_normal(
    servico, model_pricing_factory, monkeypatch
):
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderStreamFake())

    eventos = await _coleta(
        servico, prompt="Qual a posologia da amoxicilina para adulto?", mode="QUICK_SEARCH"
    )

    nomes = [e for e, _ in eventos]
    assert nomes[0] == "start", f"O primeiro evento deveria ser 'start', veio {nomes[:3]}"
    assert nomes[-1] == "done", f"O último evento deveria ser 'done', veio {nomes[-3:]}"
    assert "token" in nomes, "Nenhum token foi emitido"
    assert "error" not in nomes


async def test_tokens_remontam_a_resposta(servico, model_pricing_factory, monkeypatch):
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    monkeypatch.setitem(
        ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity",
        ProviderStreamFake(pedacos=("Amoxicilina ", "500mg ", "8/8h.")),
    )

    eventos = await _coleta(servico, prompt="Posologia da amoxicilina?", mode="QUICK_SEARCH")

    texto = "".join(d["text"] for e, d in eventos if e == "token")
    assert texto == "Amoxicilina 500mg 8/8h."


# ── Falhas ───────────────────────────────────────────────────────────────

async def test_modelo_inexistente_emite_error(servico, monkeypatch):
    """Modelo fora da tabela de preços vira evento de erro, não exceção crua."""
    eventos = await _coleta(servico, prompt="Pergunta clínica qualquer", mode="QUICK_SEARCH")

    nomes = [e for e, _ in eventos]
    assert "error" in nomes


async def test_erro_nao_vaza_detalhe_interno(servico, model_pricing_factory, monkeypatch):
    """Mensagem de erro para o usuário não pode carregar stack trace nem SQL."""
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    monkeypatch.setitem(
        ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderStreamQueFalha()
    )

    eventos = await _coleta(servico, prompt="Pergunta clínica qualquer", mode="QUICK_SEARCH")

    erros = [d for e, d in eventos if e == "error"]
    if erros:
        texto = json.dumps(erros, ensure_ascii=False)
        assert "Traceback" not in texto
        assert "SELECT" not in texto.upper()


# ── DLP no caminho do streaming ──────────────────────────────────────────

async def test_prompt_do_stream_e_sanitizado(servico, db, model_pricing_factory, monkeypatch):
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderStreamFake())

    await _coleta(
        servico,
        prompt="Paciente Maria Silva, CPF 123.456.789-00, com tosse produtiva",
        mode="QUICK_SEARCH",
    )

    from sqlalchemy import select

    from app.models.models import Interaction

    interacoes = (await db.execute(select(Interaction))).scalars().all()
    assert interacoes, "A interação deveria ter sido persistida"
    for i in interacoes:
        assert "123.456.789-00" not in i.prompt_text
        assert "Maria Silva" not in i.prompt_text


# ── Fallback entre provedores ────────────────────────────────────────────
# Se o modelo primário do modo falha no meio do stream, o serviço tenta uma
# lista de modelos alternativos via `complete` (não streaming) e devolve o
# texto de uma vez. É o que separa "indisponibilidade" de "resposta pior".

class ProviderCompleteFake:
    """Responde só por `complete` — é assim que o fallback é chamado."""

    def __init__(self, texto="resposta do fallback"):
        self.texto = texto
        self.chamado_com: list[str] = []

    async def complete(self, model_id, prompt, **kwargs):
        from app.services.integracoes.ai_providers import ProviderResponse

        self.chamado_com.append(model_id)
        return ProviderResponse(text=self.texto, tokens_in=10, tokens_out=20)

    async def stream(self, model_id, prompt, **kwargs):
        raise AssertionError("O fallback deve usar complete, não stream")
        yield  # pragma: no cover


async def test_falha_do_primario_cai_no_fallback(
    servico, db, model_pricing_factory, monkeypatch
):
    """QUICK_SEARCH: primário é sonar-pro (perplexity); fallback é gemini-2.5-flash."""
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    await model_pricing_factory(model_id="gemini-2.5-flash", provider_type="google")

    fallback = ProviderCompleteFake("Amoxicilina 500mg de 8/8h por 7 dias.")
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderStreamQueFalha())
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "google", fallback)

    eventos = await _coleta(servico, prompt="Posologia da amoxicilina?", mode="QUICK_SEARCH")

    nomes = [e for e, _ in eventos]
    assert nomes[-1] == "done", f"Deveria completar via fallback, veio {nomes[-3:]}"
    assert fallback.chamado_com == ["gemini-2.5-flash"]

    texto = "".join(d["text"] for e, d in eventos if e == "token")
    assert "Amoxicilina" in texto


async def test_fallback_e_marcado_como_tal(servico, db, model_pricing_factory, monkeypatch):
    """
    `is_fallback` precisa ficar registrado: sem isso não há como medir com que
    frequência o provedor primário está falhando em produção.
    """
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    await model_pricing_factory(model_id="gemini-2.5-flash", provider_type="google")
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderStreamQueFalha())
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "google", ProviderCompleteFake())

    await _coleta(servico, prompt="Posologia da amoxicilina?", mode="QUICK_SEARCH")

    from sqlalchemy import select

    from app.models.models import InteractionResponse

    respostas = (await db.execute(select(InteractionResponse))).scalars().all()
    assert respostas, "A resposta do fallback deveria ter sido persistida"
    assert any(r.is_fallback for r in respostas)
    assert any(r.model_used == "gemini-2.5-flash" for r in respostas)


async def test_todos_os_fallbacks_falhando_devolve_mensagem_amigavel(
    servico, model_pricing_factory, monkeypatch
):
    """Último recurso: mensagem para o usuário, não exceção nem stream vazio."""
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    await model_pricing_factory(model_id="gemini-2.5-flash", provider_type="google")

    class TudoFalha:
        async def complete(self, *a, **k):
            raise RuntimeError("também fora do ar")

        async def stream(self, *a, **k):
            raise RuntimeError("também fora do ar")
            yield  # pragma: no cover

    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderStreamQueFalha())
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "google", TudoFalha())

    eventos = await _coleta(servico, prompt="Posologia da amoxicilina?", mode="QUICK_SEARCH")

    texto = "".join(d["text"] for e, d in eventos if e == "token")
    assert "não foi possível processar" in texto
    assert "Traceback" not in texto


async def test_fallback_sem_modelo_cadastrado_e_pulado(
    servico, model_pricing_factory, monkeypatch
):
    """
    Modelo de fallback ausente da tabela de preços é pulado sem quebrar —
    o serviço segue para o próximo da lista ou para a mensagem final.
    """
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    # gemini-2.5-flash deliberadamente NÃO cadastrado
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderStreamQueFalha())

    eventos = await _coleta(servico, prompt="Posologia da amoxicilina?", mode="QUICK_SEARCH")

    texto = "".join(d["text"] for e, d in eventos if e == "token")
    assert "não foi possível processar" in texto


# ── text_done: o texto entregue antes dos metadados ──────────────────────
# O `done` só sai depois de PubMed, classificação e extração de medicamentos —
# segundos de rede. Até existir o `text_done`, o cliente mantinha a digitação
# bloqueada nesse intervalo, com a resposta inteira já visível na tela.

async def test_text_done_sai_entre_o_ultimo_token_e_o_done(
    servico, model_pricing_factory, monkeypatch
):
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderStreamFake())

    eventos = await _coleta(servico, prompt="Posologia da amoxicilina?", mode="QUICK_SEARCH")

    nomes = [e for e, _ in eventos]
    assert "text_done" in nomes, f"evento ausente; vieram {nomes}"
    i = nomes.index("text_done")
    assert nomes[i - 1] == "token", "text_done deve vir logo depois do último token"
    assert nomes[-1] == "done"
    assert i < len(nomes) - 1, "text_done não pode ser o último evento"

    # O cliente fixa a conversa neste evento: sem o id, a próxima pergunta
    # enviada durante a espera pelos metadados abriria uma conversa nova.
    assert eventos[i][1]["conversation_id"]


async def test_text_done_precede_o_pos_processamento(
    servico, db, model_pricing_factory, monkeypatch
):
    """
    O evento tem que sair ANTES do PubMed, não junto. Se sair depois, ele não
    resolve nada — é justamente o PubMed que custa a espera.
    """
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    monkeypatch.setitem(
        ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity",
        ProviderStreamFake(pedacos=("Amoxicilina ", "500mg.")),
    )

    pubmed_chamado: list[bool] = []

    async def _pubmed_que_nunca_responde(*a, **k):
        pubmed_chamado.append(True)
        await asyncio.sleep(3600)

    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.validate_with_pubmed",
        _pubmed_que_nunca_responde,
    )

    gerador = servico.stream(prompt="Posologia da amoxicilina?", mode="QUICK_SEARCH")
    nomes = []
    async for frame in gerador:
        nome, _ = parse_sse([frame])[0]
        nomes.append(nome)
        if nome == "text_done":
            break
    # Abort do cliente: é o que o navegador faz quando o médico manda a
    # próxima pergunta sem esperar as referências.
    await gerador.aclose()

    assert "text_done" in nomes
    assert not pubmed_chamado, "o pós-processamento começou antes do text_done"


async def test_abort_depois_do_text_done_nao_perde_a_resposta(
    servico, db, model_pricing_factory, monkeypatch
):
    """
    Liberar a digitação torna o abort no meio dos metadados comum. Com um commit
    só no fim, esse abort desfazia a transação inteira: o médico via a resposta
    na tela e não a encontrava mais ao reabrir a conversa.
    """
    await model_pricing_factory(model_id="sonar-pro", provider_type="perplexity")
    monkeypatch.setitem(
        ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity",
        ProviderStreamFake(pedacos=("Amoxicilina ", "500mg.")),
    )

    async def _pubmed_que_nunca_responde(*a, **k):
        await asyncio.sleep(3600)

    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.validate_with_pubmed",
        _pubmed_que_nunca_responde,
    )

    gerador = servico.stream(prompt="Posologia da amoxicilina?", mode="QUICK_SEARCH")
    async for frame in gerador:
        nome, _ = parse_sse([frame])[0]
        if nome == "text_done":
            break
    await gerador.aclose()

    from sqlalchemy import select

    from app.models.models import AuditLog, InteractionResponse

    respostas = (await db.execute(select(InteractionResponse))).scalars().all()
    assert respostas, "a resposta precisa sobreviver ao abort"
    assert respostas[0].response_text == "Amoxicilina 500mg."

    # A auditoria também: sem ela, uma interação atendida não deixaria rastro.
    auditorias = (await db.execute(select(AuditLog))).scalars().all()
    assert any(a.action == "orquestrador_stream" for a in auditorias)
