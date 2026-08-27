"""
Expurgo agendado dentro do backend.

Substituiu o cron do painel do Railway, que parou de rodar e ficou 39 dias sem
ninguém saber. O ganho não é técnico — é que o agendamento agora é código:
aparece no diff, tem estes testes, e não some sem o backend sumir junto.

Os testes que mais importam aqui são os de FALHA. Um laço que morre na primeira
exceção reproduz exatamente o problema que este módulo existe para eliminar.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.models.models import FileExtraction
from app.services import expurgo_agendado
from app.services.data_subject_service import RETENCAO_IMAGEM_DIAS, medir_passivo


async def _arquivo(db, dono, *, dias_atras: int, com_imagem: bool = True):
    extraction = FileExtraction(
        user_id=dono.id,
        file_name="exame.png",
        file_type="image" if com_imagem else "pdf",
        extracted_text="conteúdo",
        image_base64="QUJD" if com_imagem else None,
        image_media_type="image/png" if com_imagem else None,
        created_at=datetime.now(UTC) - timedelta(days=dias_atras),
    )
    db.add(extraction)
    await db.flush()
    return extraction


# ── Medição ──────────────────────────────────────────────────────────────────

async def test_banco_em_dia_nao_tem_passivo(db, user):
    await _arquivo(db, user, dias_atras=3)
    assert (await medir_passivo(db))["total"] == 0


async def test_imagem_vencida_entra_no_passivo_com_o_atraso(db, user):
    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 10)

    passivo = await medir_passivo(db)

    assert passivo["imagens_vencidas"] == 1
    assert passivo["dias_de_atraso"] == 10


async def test_imagem_ja_expurgada_nao_conta_de_novo(db, user):
    """
    O expurgo zera `image_base64` e mantém a linha. Contá-la outra vez faria o
    alarme gritar para sempre depois da primeira limpeza — e alarme que sempre
    grita é alarme que ninguém lê.
    """
    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 10, com_imagem=False)

    assert (await medir_passivo(db))["imagens_vencidas"] == 0


async def test_atraso_vem_do_registro_mais_antigo(db, user):
    """Dizer "há passivo" não distingue um dia de esquecimento de um trimestre."""
    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 2)
    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 40)

    assert (await medir_passivo(db))["dias_de_atraso"] == 40


# ── Uma rodada ───────────────────────────────────────────────────────────────

async def test_rodada_apaga_o_vencido(db, db_conn, user, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    vencido = await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 5)
    monkeypatch.setattr(
        expurgo_agendado, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )

    await expurgo_agendado._uma_rodada()
    await db.refresh(vencido)

    assert vencido.image_base64 is None


async def test_rodada_alarma_quando_estava_atrasada(db, db_conn, user, monkeypatch):
    """O atraso é medido ANTES de limpar — senão a evidência some com o dado."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 30)
    monkeypatch.setattr(
        expurgo_agendado, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )
    alarmes = []
    monkeypatch.setattr(expurgo_agendado, "_alertar", alarmes.append)

    await expurgo_agendado._uma_rodada()

    assert len(alarmes) == 1
    assert alarmes[0]["dias_de_atraso"] == 30


async def test_rodada_em_dia_nao_alarma(db, db_conn, user, monkeypatch):
    """Alarmar a cada rodada normal treinaria todo mundo a ignorar o alarme."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 1)
    monkeypatch.setattr(
        expurgo_agendado, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )
    alarmes = []
    monkeypatch.setattr(expurgo_agendado, "_alertar", alarmes.append)

    await expurgo_agendado._uma_rodada()

    assert alarmes == []


# ── Resiliência do laço ──────────────────────────────────────────────────────

async def test_falha_numa_rodada_nao_mata_o_laco(monkeypatch):
    """
    O teste central deste arquivo. Um erro transitório de banco não pode
    encerrar o agendamento em silêncio — seria recriar, dentro do processo, o
    mesmo modo de falha do cron que morreu no painel.
    """
    chamadas = []

    async def _rodada_que_falha_uma_vez():
        chamadas.append(1)
        if len(chamadas) == 1:
            raise RuntimeError("banco indisponível")

    monkeypatch.setattr(expurgo_agendado, "_uma_rodada", _rodada_que_falha_uma_vez)
    monkeypatch.setattr(expurgo_agendado, "ATRASO_INICIAL_SEGUNDOS", 0)
    monkeypatch.setattr(expurgo_agendado, "INTERVALO_HORAS", 0.0001)

    tarefa = expurgo_agendado.iniciar()
    await asyncio.sleep(0.4)
    await expurgo_agendado.parar(tarefa)

    assert len(chamadas) >= 2, "o laço parou na primeira falha"


async def test_parar_encerra_a_tarefa(monkeypatch):
    async def _nada():
        return None

    monkeypatch.setattr(expurgo_agendado, "_uma_rodada", _nada)
    monkeypatch.setattr(expurgo_agendado, "ATRASO_INICIAL_SEGUNDOS", 0)

    tarefa = expurgo_agendado.iniciar()
    await expurgo_agendado.parar(tarefa)

    assert tarefa.done()


async def test_parar_aceita_tarefa_inexistente():
    """Shutdown não pode explodir se o startup nem chegou a criar a tarefa."""
    await expurgo_agendado.parar(None)


def test_alerta_sem_sentry_nao_explode(monkeypatch):
    """Sem DSN o alarme é no-op — em desenvolvimento o log basta."""
    expurgo_agendado._alertar({"total": 1, "dias_de_atraso": 5})


@pytest.mark.parametrize("dias", [0, 1, 2])
def test_atraso_dentro_da_tolerancia_nao_e_alarme(dias):
    """Deploy, reinício e fuso produzem um dia de atraso sem significar nada."""
    assert dias <= expurgo_agendado.ATRASO_TOLERADO_DIAS
