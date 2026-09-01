"""
Backfill de `specialty_slug` a partir do texto livre da base antiga.

O risco deste script não é falhar — é FUNCIONAR ERRADO em massa e em silêncio:
um alias equivocado reescreve a especialidade de muita gente, e ninguém reclama
de receber conteúdo levemente fora do alvo. Daí o dry-run ser o padrão e estes
testes cobrirem, antes de tudo, o que ele NÃO pode fazer.
"""

import pytest

from app.medicina import identidade
from scripts import normalizar_especialidades

pytestmark = pytest.mark.asyncio


async def test_dry_run_nao_grava(db, user_factory, monkeypatch, capsys):
    user = await user_factory()
    user.specialty = "Cardiologia"
    await db.flush()

    monkeypatch.setattr(
        normalizar_especialidades, "async_session_factory", lambda: _sessao(db)
    )
    await normalizar_especialidades.executar(aplicar=False, limite=None)

    await db.refresh(user)
    assert user.specialty_slug is None
    assert "DRY-RUN" in capsys.readouterr().out


async def test_aplicar_normaliza_e_marca_como_declarado(db, user_factory, monkeypatch):
    user = await user_factory()
    user.specialty = "Cardiologia"
    await db.flush()

    monkeypatch.setattr(
        normalizar_especialidades, "async_session_factory", lambda: _sessao(db)
    )
    await normalizar_especialidades.executar(aplicar=True, limite=None)

    await db.refresh(user)
    assert user.specialty_slug == "cardiologia"
    assert user.specialties == ["cardiologia"]
    # `declarado` é a verdade: aquele texto foi digitado pelo médico no
    # onboarding antigo. Marcar como `cadastro` daria a ele autoridade que não
    # tem, e impediria o webhook de corrigir depois.
    assert user.specialty_source == identidade.FONTE_DECLARADO


async def test_texto_nao_reconhecido_e_preservado(db, user_factory, monkeypatch, capsys):
    """Destruir o original tornaria o defeito irrecuperável.

    A lista de não-resolvidos é o insumo para novos aliases — é ela que precisa
    ser lida por uma pessoa.
    """
    user = await user_factory()
    user.specialty = "Cardiologia Intervencionista"
    await db.flush()

    monkeypatch.setattr(
        normalizar_especialidades, "async_session_factory", lambda: _sessao(db)
    )
    await normalizar_especialidades.executar(aplicar=True, limite=None)

    await db.refresh(user)
    assert user.specialty == "Cardiologia Intervencionista"  # intacto
    assert user.specialty_slug is None
    assert "NÃO reconhecidos" in capsys.readouterr().out


async def test_nao_sobrescreve_quem_ja_tem_fonte_melhor(db, user_factory, monkeypatch):
    """Quem já foi preenchido pelo grupo `[CFM]` não entra na varredura."""
    user = await user_factory()
    identidade.aplicar_especialidade(
        user, slug="cardiologia", fonte=identidade.FONTE_CADASTRO
    )
    await db.flush()

    monkeypatch.setattr(
        normalizar_especialidades, "async_session_factory", lambda: _sessao(db)
    )
    await normalizar_especialidades.executar(aplicar=True, limite=None)

    await db.refresh(user)
    assert user.specialty_source == identidade.FONTE_CADASTRO


def _sessao(db):
    """Empresta a sessão do teste ao script, sem fechá-la no fim do `async with`."""
    class Emprestada:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *a):
            return False

    return Emprestada()
