"""
Vigilância das garantias silenciosas.

O módulo sob teste existe porque o cache semântico ficou meses sem gravar uma
linha, com `interactions.cache_hit` registrado o tempo todo. O dado estava lá;
ninguém perguntava.

Os testes que mais importam aqui são os de NÃO-ALARME. Um alarme que dispara
sem motivo é pior que alarme nenhum: ele treina o time a arquivar sem ler, e a
próxima falha silenciosa passa igual — agora com falsa sensação de cobertura.
Por isso cada limiar tem um teste do lado de dentro e outro do lado de fora.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.models import AuditLog, Interaction, SemanticCache
from app.services import expurgo_agendado, vigilancia_agendada
from app.services.vigilancia_service import (
    ACAO_EXPURGO,
    ATRASO_TOLERADO_EXPURGO_DIAS,
    CUSTO_MINIMO_PARA_COMPARAR,
    FATOR_ESCALADA_CUSTO,
    MIN_AMOSTRA_CACHE,
    avaliar,
    medir_cache_semantico,
    medir_custo,
    medir_ultimo_expurgo,
)

EMBEDDING_FALSO = [0.0] * 1536


# ── Fábricas ─────────────────────────────────────────────────────────────────

async def _interacao(
    db, conv, dono, *,
    mode="CLINICAL_REASONING",
    cache_hit=False,
    custo="0",
    dias_atras=0,
):
    quando = datetime.now(UTC) - timedelta(days=dias_atras)
    interaction = Interaction(
        conversation_id=conv.id,
        user_id=dono.id,
        feature="ORQUESTRADOR",
        mode=mode,
        prompt_text="pergunta de teste",
        cache_hit=cache_hit,
        token_cost_usd=Decimal(custo),
        created_at=quando,
        started_at=quando,
    )
    db.add(interaction)
    await db.flush()
    return interaction


async def _entrada_de_cache(db, *, dias_para_expirar=30):
    entrada = SemanticCache(
        mode="QUICK_SEARCH",
        normalized_prompt="pneumonia adquirida na comunidade",
        prompt_embedding=EMBEDDING_FALSO,
        response_json={"texto": "resposta"},
        expires_at=datetime.now(UTC) + timedelta(days=dias_para_expirar),
    )
    db.add(entrada)
    await db.flush()
    return entrada


def _medicoes(*, cache=None, custo=None, expurgo=None) -> dict:
    """Medições saudáveis por padrão; cada teste desloca só o que lhe interessa."""
    return {
        "cache": {"janela_dias": 7, "elegiveis": 200, "hits": 40,
                  "taxa_hit": 0.2, "linhas_vigentes": 120, **(cache or {})},
        "custo": {"janela_dias": 7, "custo_usd": 30.0,
                  "custo_usd_anterior": 25.0, "fator": 1.2, **(custo or {})},
        "expurgo": {"nunca_registrado": False, "dias_desde": 0,
                    "ultimo_em": "2026-08-28T00:00:00+00:00", **(expurgo or {})},
    }


@pytest.fixture(autouse=True)
def _sem_memoria_de_alarme():
    """
    O silenciador de alarmes repetidos é um dict de módulo. Sem limpar, um teste
    que alarma faz o seguinte achar que já alarmou hoje — e o segundo passaria
    verde pelo motivo errado.
    """
    vigilancia_agendada._ultimo_alarme.clear()
    yield
    vigilancia_agendada._ultimo_alarme.clear()


# ── Medição: cache semântico ─────────────────────────────────────────────────

async def test_sem_trafego_o_cache_nao_afirma_nada(db):
    medida = await medir_cache_semantico(db)

    assert medida["elegiveis"] == 0
    assert medida["taxa_hit"] == 0.0


async def test_conta_elegiveis_e_hits(db, user, conversation_factory):
    conv = await conversation_factory(user)
    await _interacao(db, conv, user, cache_hit=True)
    await _interacao(db, conv, user, cache_hit=True)
    await _interacao(db, conv, user, cache_hit=False)

    medida = await medir_cache_semantico(db)

    assert medida["elegiveis"] == 3
    assert medida["hits"] == 2
    assert medida["taxa_hit"] == pytest.approx(0.6667, abs=1e-4)


async def test_modo_que_nao_consulta_o_cache_fica_de_fora(db, user, conversation_factory):
    """
    Contar PRODUCTIVITY como elegível diluiria a taxa com interações que nunca
    passam pelo cache — a métrica cairia sem nada ter quebrado.
    """
    conv = await conversation_factory(user)
    await _interacao(db, conv, user, mode="QUICK_SEARCH")
    await _interacao(db, conv, user, mode="PRODUCTIVITY")
    await _interacao(db, conv, user, mode="EXAM_REVIEW")

    assert (await medir_cache_semantico(db))["elegiveis"] == 1


async def test_interacao_fora_da_janela_nao_conta(db, user, conversation_factory):
    conv = await conversation_factory(user)
    await _interacao(db, conv, user, dias_atras=30)

    assert (await medir_cache_semantico(db, janela_dias=7))["elegiveis"] == 0


async def test_entrada_expirada_nao_conta_como_vigente(db):
    """
    Uma tabela cheia de lixo vencido não é prova de que a escrita funciona —
    e é exatamente essa a pergunta que a contagem responde.
    """
    await _entrada_de_cache(db, dias_para_expirar=-1)

    assert (await medir_cache_semantico(db))["linhas_vigentes"] == 0


async def test_entrada_vigente_conta(db):
    await _entrada_de_cache(db)

    assert (await medir_cache_semantico(db))["linhas_vigentes"] == 1


# ── Medição: custo ───────────────────────────────────────────────────────────

async def test_custo_separa_as_duas_janelas(db, user, conversation_factory):
    conv = await conversation_factory(user)
    await _interacao(db, conv, user, custo="10.00", dias_atras=1)
    await _interacao(db, conv, user, custo="5.00", dias_atras=2)
    await _interacao(db, conv, user, custo="2.00", dias_atras=9)   # janela anterior

    medida = await medir_custo(db, janela_dias=7)

    assert medida["custo_usd"] == pytest.approx(15.0)
    assert medida["custo_usd_anterior"] == pytest.approx(2.0)


async def test_custo_sem_historico_nao_calcula_fator(db):
    """Dividir por zero aqui derrubaria a rodada inteira de vigilância."""
    assert (await medir_custo(db))["fator"] is None


# ── Medição: expurgo ─────────────────────────────────────────────────────────

async def test_sem_rastro_de_expurgo(db):
    assert (await medir_ultimo_expurgo(db))["nunca_registrado"] is True


async def test_dias_desde_vem_da_rodada_mais_recente(db):
    for dias in (10, 3, 40):
        db.add(AuditLog(
            action=ACAO_EXPURGO,
            created_at=datetime.now(UTC) - timedelta(days=dias),
        ))
    await db.flush()

    medida = await medir_ultimo_expurgo(db)

    assert medida["nunca_registrado"] is False
    assert medida["dias_desde"] == 3


async def test_outra_acao_de_auditoria_nao_conta_como_expurgo(db):
    """
    `audit_logs` guarda ações de gente também. Confundir um convite gerado com
    uma rodada de expurgo faria o alarme calar justamente quando o produto tem
    uso — o pior momento possível.
    """
    db.add(AuditLog(action="invite.generate"))
    await db.flush()

    assert (await medir_ultimo_expurgo(db))["nunca_registrado"] is True


# ── Decisão: silêncio no caso saudável ───────────────────────────────────────

def test_sistema_saudavel_nao_alarma():
    assert avaliar(_medicoes()) == []


# ── Decisão: cache ───────────────────────────────────────────────────────────

def test_cache_vazio_com_trafego_alarma():
    """O defeito real: escrita desligada em silêncio, tabela vazia."""
    alarmes = avaliar(_medicoes(cache={"elegiveis": MIN_AMOSTRA_CACHE, "linhas_vigentes": 0}))

    assert [a["tag"] for a in alarmes] == ["cache_semantico_sem_escrita"]


def test_cache_vazio_sem_volume_nao_alarma():
    """
    Com pouco tráfego, "tabela vazia" é indistinguível de "ninguém perguntou
    nada cacheável". Alarmar aqui seria adivinhação — e um alarme por semana
    num ambiente de baixo uso mataria a credibilidade do resto.
    """
    alarmes = avaliar(_medicoes(cache={"elegiveis": MIN_AMOSTRA_CACHE - 1, "linhas_vigentes": 0}))

    assert alarmes == []


def test_taxa_de_hit_zero_com_tabela_populada_nao_alarma():
    """
    Taxa baixa pode ser legítima: perguntas todas diferentes. O sinal forte é a
    ausência de ESCRITA, não a ausência de acerto.
    """
    alarmes = avaliar(_medicoes(cache={"hits": 0, "taxa_hit": 0.0, "linhas_vigentes": 50}))

    assert alarmes == []


# ── Decisão: custo ───────────────────────────────────────────────────────────

def test_custo_triplicado_alarma():
    base = float(CUSTO_MINIMO_PARA_COMPARAR)
    alarmes = avaliar(_medicoes(custo={
        "custo_usd": base * float(FATOR_ESCALADA_CUSTO),
        "custo_usd_anterior": base,
        "fator": float(FATOR_ESCALADA_CUSTO),
    }))

    assert [a["tag"] for a in alarmes] == ["custo_escalando"]


def test_custo_pequeno_multiplicado_nao_alarma():
    """US$ 0,10 virando US$ 1,00 é 10x e não significa nada."""
    alarmes = avaliar(_medicoes(custo={
        "custo_usd": 1.0, "custo_usd_anterior": 0.1, "fator": 10.0,
    }))

    assert alarmes == []


def test_crescimento_normal_nao_alarma():
    alarmes = avaliar(_medicoes(custo={
        "custo_usd": 40.0, "custo_usd_anterior": 25.0, "fator": 1.6,
    }))

    assert alarmes == []


# ── Decisão: expurgo ─────────────────────────────────────────────────────────

def test_expurgo_sem_rastro_alarma():
    alarmes = avaliar(_medicoes(expurgo={"nunca_registrado": True, "dias_desde": None,
                                         "ultimo_em": None}))

    assert [a["tag"] for a in alarmes] == ["expurgo_sem_rastro"]


def test_expurgo_parado_alarma():
    alarmes = avaliar(_medicoes(expurgo={"dias_desde": ATRASO_TOLERADO_EXPURGO_DIAS + 1}))

    assert [a["tag"] for a in alarmes] == ["expurgo_parado"]


@pytest.mark.parametrize("dias", [0, 1, ATRASO_TOLERADO_EXPURGO_DIAS])
def test_atraso_dentro_da_tolerancia_nao_alarma(dias):
    """Deploy, reinício e fuso produzem um dia de atraso sem significar nada."""
    assert avaliar(_medicoes(expurgo={"dias_desde": dias})) == []


def test_alarmes_independentes_se_acumulam():
    alarmes = avaliar(_medicoes(
        cache={"elegiveis": 500, "linhas_vigentes": 0},
        expurgo={"nunca_registrado": True, "dias_desde": None, "ultimo_em": None},
    ))

    assert {a["tag"] for a in alarmes} == {"cache_semantico_sem_escrita", "expurgo_sem_rastro"}


# ── Integração: o expurgo deixa o rastro que a vigilância procura ────────────

async def test_rodada_de_expurgo_deixa_rastro_auditavel(db, db_conn, user, monkeypatch):
    """
    A costura entre os dois módulos. Se o expurgo parar de gravar o AuditLog, a
    vigilância passa a alarmar todo dia dizendo que o expurgo morreu — um falso
    positivo diário, que é o jeito mais rápido de fazer o time desligar tudo.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(
        expurgo_agendado, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )
    assert (await medir_ultimo_expurgo(db))["nunca_registrado"] is True

    await expurgo_agendado._uma_rodada()

    medida = await medir_ultimo_expurgo(db)
    assert medida["nunca_registrado"] is False
    assert medida["dias_desde"] == 0


# ── Laço agendado ────────────────────────────────────────────────────────────

async def test_rodada_alarma_o_que_avaliar_devolveu(db_conn, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(
        vigilancia_agendada, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )
    monkeypatch.setattr(
        vigilancia_agendada, "avaliar",
        lambda _m: [{"tag": "teste", "mensagem": "algo", "contexto": {}}],
    )
    enviados = []
    monkeypatch.setattr(vigilancia_agendada, "alarmar",
                        lambda **kw: enviados.append(kw["tag"]))

    await vigilancia_agendada._uma_rodada()

    assert enviados == ["teste"]


async def test_rodada_saudavel_nao_alarma(db_conn, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setattr(
        vigilancia_agendada, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )
    monkeypatch.setattr(vigilancia_agendada, "avaliar", lambda _m: [])
    enviados = []
    monkeypatch.setattr(vigilancia_agendada, "alarmar",
                        lambda **kw: enviados.append(kw["tag"]))

    await vigilancia_agendada._uma_rodada()

    assert enviados == []


def test_mesma_tag_nao_alarma_duas_vezes_no_mesmo_dia():
    """Alarme repetido de hora em hora é como se ensina alguém a ignorá-lo."""
    assert vigilancia_agendada._deve_alarmar("cache_semantico_sem_escrita") is True
    assert vigilancia_agendada._deve_alarmar("cache_semantico_sem_escrita") is False


def test_tags_diferentes_nao_se_silenciam():
    assert vigilancia_agendada._deve_alarmar("cache_semantico_sem_escrita") is True
    assert vigilancia_agendada._deve_alarmar("expurgo_parado") is True


def test_silencio_expira():
    agora = datetime.now(UTC)
    depois = agora + timedelta(hours=vigilancia_agendada.SILENCIO_POR_TAG_HORAS + 1)

    assert vigilancia_agendada._deve_alarmar("custo_escalando", agora) is True
    assert vigilancia_agendada._deve_alarmar("custo_escalando", depois) is True


async def test_falha_numa_rodada_nao_mata_o_laco(monkeypatch):
    """
    Mesmo teste central de `expurgo_agendado`, pelo mesmo motivo: um laço que
    morre na primeira exceção recria, dentro do processo, o modo de falha que
    este módulo existe para eliminar. Aqui dói em dobro — é o vigia morrendo
    calado.
    """
    chamadas = []

    async def _rodada_que_falha_uma_vez():
        chamadas.append(1)
        if len(chamadas) == 1:
            raise RuntimeError("banco indisponível")

    monkeypatch.setattr(vigilancia_agendada, "_uma_rodada", _rodada_que_falha_uma_vez)
    monkeypatch.setattr(vigilancia_agendada, "ATRASO_INICIAL_SEGUNDOS", 0)
    monkeypatch.setattr(vigilancia_agendada, "INTERVALO_HORAS", 0.0001)

    tarefa = vigilancia_agendada.iniciar()
    await asyncio.sleep(0.4)
    await vigilancia_agendada.parar(tarefa)

    assert len(chamadas) >= 2, "o laço parou na primeira falha"


async def test_parar_encerra_a_tarefa(monkeypatch):
    async def _nada():
        return None

    monkeypatch.setattr(vigilancia_agendada, "_uma_rodada", _nada)
    monkeypatch.setattr(vigilancia_agendada, "ATRASO_INICIAL_SEGUNDOS", 0)

    tarefa = vigilancia_agendada.iniciar()
    await vigilancia_agendada.parar(tarefa)

    assert tarefa.done()


async def test_parar_aceita_tarefa_inexistente():
    await vigilancia_agendada.parar(None)


def test_vigilancia_roda_depois_do_expurgo_no_boot():
    """
    A vigilância alarma quando não acha rastro de expurgo. Se ela rodasse
    primeiro, todo boot de banco novo produziria um alarme falso. A ordem é uma
    dependência real entre dois módulos, e nada além deste teste a protege.
    """
    assert (
        vigilancia_agendada.ATRASO_INICIAL_SEGUNDOS
        > expurgo_agendado.ATRASO_INICIAL_SEGUNDOS
    )


def test_alarme_sem_sentry_nao_explode():
    """Sem DSN o alarme é no-op — em desenvolvimento e no CI o log basta."""
    from app.core.alarme import alarmar

    assert alarmar(tag="teste", mensagem="oi", contexto={"a": 1}) is False


class _EscopoFalso:
    def __init__(self):
        self.nivel = None
        self.tags: dict[str, str] = {}
        self.contextos: dict[str, dict] = {}

    def set_level(self, nivel):
        self.nivel = nivel

    def set_tag(self, chave, valor):
        self.tags[chave] = valor

    def set_context(self, chave, valor):
        self.contextos[chave] = valor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _SentryFalso:
    """Dublê da superfície do sentry-sdk 2.x que `alarme.py` usa."""

    def __init__(self, ativo=True):
        self._ativo = ativo
        self.escopo = _EscopoFalso()
        self.mensagens: list[str] = []

    def get_client(self):
        return self

    def is_active(self):
        return self._ativo

    def new_scope(self):
        return self.escopo

    def capture_message(self, mensagem):
        self.mensagens.append(mensagem)


def test_alarme_chega_ao_sentry_com_tag_nivel_e_contexto(monkeypatch):
    """
    O que faz o alarme ser encontrável meses depois é a TAG — é por ela que o
    runbook manda procurar. Sem este teste, trocar `set_tag` por `set_extra`
    passaria verde e só apareceria no próximo incidente, procurando um filtro
    que não existe mais.
    """
    import sys

    from app.core.alarme import alarmar

    falso = _SentryFalso()
    monkeypatch.setitem(sys.modules, "sentry_sdk", falso)

    enviado = alarmar(tag="expurgo_parado", mensagem="parado há 9 dias",
                      contexto={"dias_desde": 9})

    assert enviado is True
    assert falso.mensagens == ["parado há 9 dias"]
    assert falso.escopo.tags["alarme"] == "expurgo_parado"
    assert falso.escopo.nivel == "warning"
    assert falso.escopo.contextos["expurgo_parado"] == {"dias_desde": 9}


def test_sentry_desligado_no_meio_do_caminho_nao_envia(monkeypatch):
    import sys

    from app.core.alarme import alarmar

    monkeypatch.setitem(sys.modules, "sentry_sdk", _SentryFalso(ativo=False))

    assert alarmar(tag="teste", mensagem="oi") is False


def test_falha_do_sentry_nao_derruba_quem_chamou(monkeypatch):
    """
    Um alarme que explode leva junto a rodada de expurgo — o efeito seria parar
    de cumprir a retenção por causa do mecanismo que avisa sobre ela.
    """
    import sys

    from app.core.alarme import alarmar

    class _Explode:
        def get_client(self):
            raise RuntimeError("Sentry indisponível")

    monkeypatch.setitem(sys.modules, "sentry_sdk", _Explode())

    assert alarmar(tag="teste", mensagem="oi") is False
