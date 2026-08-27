"""
Alarme de expurgo atrasado.

A política de retenção existe e está correta; o que falhou foi o AGENDAMENTO,
no painel do Railway, fora do repositório. O Railway não notifica falha de cron,
então em 2026-08-27 havia 39 dias de passivo sem ninguém saber.

Estes testes cobrem a medição — a parte que decide se o alarme dispara. O envio
ao Sentry não é exercitado contra o serviço real; o que importa aqui é que a
contagem esteja certa, porque um alarme que conta errado é pior que alarme
nenhum: ou cria ruído, ou cala quando deveria gritar.
"""

from datetime import UTC, datetime, timedelta

from app.models.models import FileExtraction
from app.services.data_subject_service import (
    RETENCAO_ARQUIVO_DIAS,
    RETENCAO_IMAGEM_DIAS,
)


async def _arquivo(db, dono, *, dias_atras: int, com_imagem: bool):
    criado = datetime.now(UTC) - timedelta(days=dias_atras)
    extraction = FileExtraction(
        user_id=dono.id,
        file_name="exame.png" if com_imagem else "laudo.pdf",
        file_type="image" if com_imagem else "pdf",
        extracted_text="conteúdo",
        image_base64="QUJD" if com_imagem else None,
        image_media_type="image/png" if com_imagem else None,
        created_at=criado,
    )
    db.add(extraction)
    await db.flush()
    return extraction


async def test_banco_em_dia_nao_dispara_alarme(db, user, monkeypatch):
    from scripts import verificar_expurgo

    monkeypatch.setattr(verificar_expurgo, "async_session_factory", lambda: _sessao(db))
    await _arquivo(db, user, dias_atras=3, com_imagem=True)

    passivo = await verificar_expurgo.medir_passivo()

    assert passivo["total"] == 0


async def test_imagem_alem_do_prazo_entra_no_passivo(db, user, monkeypatch):
    from scripts import verificar_expurgo

    monkeypatch.setattr(verificar_expurgo, "async_session_factory", lambda: _sessao(db))
    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 10, com_imagem=True)

    passivo = await verificar_expurgo.medir_passivo()

    assert passivo["imagens_vencidas"] == 1
    assert passivo["dias_de_atraso"] == 10


async def test_imagem_ja_expurgada_nao_conta(db, user, monkeypatch):
    """
    O expurgo zera `image_base64` e mantém a linha. Contá-la de novo faria o
    alarme gritar para sempre depois da primeira limpeza.
    """
    from scripts import verificar_expurgo

    monkeypatch.setattr(verificar_expurgo, "async_session_factory", lambda: _sessao(db))
    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 10, com_imagem=False)

    passivo = await verificar_expurgo.medir_passivo()

    assert passivo["imagens_vencidas"] == 0


async def test_arquivo_alem_do_prazo_longo_entra_no_passivo(db, user, monkeypatch):
    from scripts import verificar_expurgo

    monkeypatch.setattr(verificar_expurgo, "async_session_factory", lambda: _sessao(db))
    await _arquivo(db, user, dias_atras=RETENCAO_ARQUIVO_DIAS + 5, com_imagem=False)

    passivo = await verificar_expurgo.medir_passivo()

    assert passivo["arquivos_vencidos"] == 1


async def test_atraso_e_medido_pelo_registro_mais_antigo(db, user, monkeypatch):
    """O alarme precisa dizer há quanto tempo, não só que existe."""
    from scripts import verificar_expurgo

    monkeypatch.setattr(verificar_expurgo, "async_session_factory", lambda: _sessao(db))
    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 2, com_imagem=True)
    await _arquivo(db, user, dias_atras=RETENCAO_IMAGEM_DIAS + 40, com_imagem=True)

    passivo = await verificar_expurgo.medir_passivo()

    assert passivo["imagens_vencidas"] == 2
    assert passivo["dias_de_atraso"] == 40


def test_alerta_sem_dsn_e_no_op(monkeypatch):
    """
    Em desenvolvimento não há DSN, e o script precisa rodar mesmo assim — o
    print no terminal basta. Igual ao resto do projeto.
    """
    from app.core.config import get_settings
    from scripts import verificar_expurgo

    get_settings.cache_clear()
    monkeypatch.setenv("SENTRY_DSN", "")

    assert verificar_expurgo._alertar_sentry({"total": 1, "dias_de_atraso": 5}) is False

    get_settings.cache_clear()


class _sessao:
    """
    Empresta a sessão do teste ao script, sem fechá-la no fim.

    O script abre a própria sessão via `async_session_factory`; fechá-la aqui
    derrubaria a transação que o harness reverte ao final do teste.
    """

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_):
        return False
