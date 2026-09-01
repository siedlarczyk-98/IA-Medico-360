"""
Feed de quem tem mais de uma residência.

É o caso comum, não a exceção: Clínica Médica é pré-requisito de quase toda
residência clínica, e Cirurgia Geral das cirúrgicas. Enquanto o feed lia só
`users.specialty` (uma string), metade do conteúdo devido a esses médicos
simplesmente não aparecia — e ninguém tinha como notar, porque o feed vinha
cheio das outras fontes.

O fallback para o singular é igualmente importante: as linhas anteriores à
migration 007 só têm `specialty` preenchido. Sem ele, o deploy silenciaria o
feed da base inteira de uma vez.
"""

import pytest

from app.medicina import identidade
from app.models.news import Topic, TopicSpecialty
from app.news.taxonomia import CORE, RELEVANTE
from app.services import news_feed_service

pytestmark = pytest.mark.asyncio

CARDIO = "Cardiologia"
CLINICA = "Clínica Médica"
INFECTO = "Infectologia"


async def _tema(db, slug: str, especialidades: list[tuple[str, str]]) -> Topic:
    tema = Topic(slug=slug, nome_pt=slug.replace("-", " ").capitalize())
    db.add(tema)
    await db.flush()
    for especialidade, peso in especialidades:
        db.add(TopicSpecialty(topic_id=tema.id, specialty=especialidade, peso=peso))
    await db.flush()
    return tema


async def test_duas_residencias_recebem_a_uniao_dos_temas(db, user):
    ic = await _tema(db, "insuficiencia-cardiaca-m", [(CARDIO, CORE)])
    dm = await _tema(db, "diabetes-m", [(CLINICA, RELEVANTE)])
    await _tema(db, "hiv-m", [(INFECTO, CORE)])

    identidade.aplicar_especialidade(
        user, slugs=["cardiologia", "clinica-medica"], fonte=identidade.FONTE_CADASTRO
    )
    await db.flush()

    sugeridos = await news_feed_service.temas_sugeridos_para(
        db, identidade.rotulos_de_especialidade(user)
    )
    slugs = {t.slug for t in sugeridos}

    assert {ic.slug, dm.slug} <= slugs, "Perdeu o conteúdo de uma das residências"
    assert "hiv-m" not in slugs, "Trouxe conteúdo de especialidade que ele não tem"


async def test_tema_compartilhado_nao_duplica(db, user):
    """Os conjuntos se sobrepõem — sem `distinct` o tema apareceria duas vezes."""
    await _tema(db, "hipertensao-m", [(CARDIO, CORE), (CLINICA, RELEVANTE)])

    identidade.aplicar_especialidade(
        user, slugs=["cardiologia", "clinica-medica"], fonte=identidade.FONTE_CADASTRO
    )
    await db.flush()

    sugeridos = await news_feed_service.temas_sugeridos_para(
        db, identidade.rotulos_de_especialidade(user)
    )
    slugs = [t.slug for t in sugeridos]

    assert slugs.count("hipertensao-m") == 1


async def test_base_antiga_com_so_o_singular_continua_funcionando(db, user):
    """Linhas anteriores à migration 007: `specialties` vazio, `specialty` cheio.

    Sem o fallback, o feed de toda a base atual silenciaria no deploy.
    """
    ic = await _tema(db, "insuficiencia-cardiaca-legado", [(CARDIO, CORE)])
    user.specialty = CARDIO
    user.specialties = None
    await db.flush()

    assert identidade.rotulos_de_especialidade(user) == [CARDIO]

    sugeridos = await news_feed_service.temas_sugeridos_para(
        db, identidade.rotulos_de_especialidade(user)
    )
    assert ic.slug in {t.slug for t in sugeridos}


async def test_generalista_cai_no_piso_e_isso_e_registrado(db, user, caplog):
    """Sem especialidade, o piso age — e agora deixa rastro.

    A contagem deste log é a métrica de sucesso do trabalho de identidade: se
    não cair com o tempo, o webhook e a reconciliação não estão funcionando.
    """
    await _tema(db, "diabetes-piso", [(CLINICA, RELEVANTE)])
    user.specialty = None
    user.specialties = None
    await db.flush()

    with caplog.at_level("INFO"):
        sugeridos = await news_feed_service.temas_sugeridos_para(
            db, identidade.rotulos_de_especialidade(user)
        )

    assert sugeridos, "Generalista não pode encarar uma lista vazia"
    assert "news.piso_especialidade" in caplog.text
