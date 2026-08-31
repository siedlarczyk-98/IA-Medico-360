"""
Alarmes do módulo de notícias — a parte pura, sem banco.

`_avaliar_noticias` é função pura de propósito (mesma separação de
`vigilancia_service.avaliar`): dá para testar todo limiar sem subir Postgres, e
o script de diagnóstico consegue mostrar as mesmas medições sem alarmar ninguém.
"""

from app.services.vigilancia_service import (
    ATRASO_TOLERADO_DIGEST_DIAS,
    DIAS_SEM_PUBLICAR_ALARME,
    MIN_AMOSTRA_NOTICIAS,
    _avaliar_noticias,
)


def _medicao(**kwargs) -> dict:
    """Medição saudável, para cada teste piorar só o campo que lhe interessa."""
    base = {
        "janela_dias": 7,
        "publicados": 20,
        "sem_tema": 0,
        "fracao_sem_tema": 0.0,
        "dias_sem_publicar": 1,
        "digest_nunca_rodou": False,
        "dias_desde_digest": 0,
    }
    return {**base, **kwargs}


def _tags(medicao: dict) -> set[str]:
    return {a["tag"] for a in _avaliar_noticias(medicao)}


def test_sistema_saudavel_nao_alarma():
    assert _avaliar_noticias(_medicao()) == []


def test_medicao_ausente_nao_quebra():
    # Banco antigo, ou `medir_tudo` de uma versão anterior: a ausência da chave
    # não pode derrubar o laço de vigilância inteiro.
    assert _avaliar_noticias(None) == []


def test_tagger_parado_alarma():
    """
    A falha mais perigosa do módulo: sem tema, o artigo não casa com ninguém e o
    feed de todos esvazia — enquanto coleta, redação e publicação seguem
    reportando sucesso. Mesma assinatura do cache semântico.
    """
    tags = _tags(_medicao(publicados=20, sem_tema=18, fracao_sem_tema=0.9))
    assert "noticias_tagger_sem_tema" in tags


def test_amostra_pequena_nao_alarma_tagger():
    """
    Com poucos artigos, "todos sem tema" é indistinguível de "publicamos dois
    esta semana". Alarmar aí treina o time a ignorar a caixa de entrada.
    """
    poucos = MIN_AMOSTRA_NOTICIAS - 1
    tags = _tags(_medicao(publicados=poucos, sem_tema=poucos, fracao_sem_tema=1.0))
    assert "noticias_tagger_sem_tema" not in tags


def test_um_artigo_sem_tema_nao_alarma():
    # Artigo ocasional que a taxonomia não cobre é normal e esperado.
    tags = _tags(_medicao(publicados=20, sem_tema=1, fracao_sem_tema=0.05))
    assert "noticias_tagger_sem_tema" not in tags


def test_pipeline_parado_alarma():
    tags = _tags(_medicao(dias_sem_publicar=DIAS_SEM_PUBLICAR_ALARME + 1))
    assert "noticias_pipeline_parado" in tags


def test_fim_de_semana_nao_alarma_pipeline():
    # A coleta roda de segunda a sexta; o limiar precisa absorver o fim de semana.
    tags = _tags(_medicao(dias_sem_publicar=DIAS_SEM_PUBLICAR_ALARME))
    assert "noticias_pipeline_parado" not in tags


def test_banco_novo_sem_publicacao_nao_alarma():
    # `dias_sem_publicar=None` é banco recém-migrado, não pipeline quebrado.
    tags = _tags(_medicao(dias_sem_publicar=None))
    assert "noticias_pipeline_parado" not in tags


def test_digest_sem_rastro_alarma():
    tags = _tags(_medicao(digest_nunca_rodou=True, dias_desde_digest=None))
    assert "noticias_digest_sem_rastro" in tags


def test_digest_parado_alarma():
    """
    Zero e-mails num dia sem match é o comportamento CORRETO, e é
    indistinguível de "a tarefa morreu" — daí o heartbeat em audit_logs ser
    medido separadamente da contagem de envios.
    """
    tags = _tags(_medicao(dias_desde_digest=ATRASO_TOLERADO_DIGEST_DIAS + 1))
    assert "noticias_digest_parado" in tags


def test_digest_recente_nao_alarma():
    tags = _tags(_medicao(dias_desde_digest=ATRASO_TOLERADO_DIGEST_DIAS))
    assert "noticias_digest_parado" not in tags
