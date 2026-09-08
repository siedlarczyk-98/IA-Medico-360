"""
Paridade entre `/query` e `/stream` no cache semântico, e o gate de contexto
de paciente.

Dois defeitos que a revisão de segurança encontrou, com a mesma raiz — os dois
caminhos do orquestrador divergiram:

1. O `/query` devolvia o payload do cache CRU, com `conversation_id` e
   `interaction_id` da interação que o populou — de outro médico. O `/stream`
   já corrigia isso, com comentário explicando o risco; a correção nunca foi
   propagada. De quebra, o `/query` não gravava Interaction no hit, então
   `vigilancia_service` ficava cega para metade do tráfego.

2. O cache servia resposta CONDICIONADA A PACIENTE. A chave é
   `(modo, prompt_sanitizado)`, sem usuário e sem pasta — mas a resposta é
   gerada com a evolução do paciente injetada. "Qual anti-hipertensivo
   escolher?" dentro da pasta de alguém com DRC produz conduta calibrada para
   aquela função renal, e o próximo médico com a mesma pergunta receberia
   aquilo. Vazamento de dado clínico E risco clínico.

Os testes leem o CÓDIGO-FONTE de propósito: o que precisa ser travado é a
estrutura dos dois caminhos, e exercitar o fluxo inteiro exigiria simular
provider, cache e banco — um teste que passaria por motivo errado.
"""

import pytest

# ── Paridade /query ↔ /stream no cache hit ───────────────────────────────────
# O docstring deste arquivo descrevia o bug com precisão, mas a correção só
# tinha sido aplicada ao `/stream`. O `/query` seguiu devolvendo o dicionário
# do cache cru — com o `conversation_id` de outro médico — por todo esse tempo.

def _fonte(modulo) -> str:
    import inspect
    return inspect.getsource(modulo)


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_query_sobrescreve_os_ids_do_cache():
    """O `/query` não pode devolver o payload do cache cru.

    Os ids de lá são da interação que POPULOU o cache, de outro usuário.
    """
    from app.services import orquestrador_service

    fonte = _fonte(orquestrador_service)
    i = fonte.find("if cached is not None:")
    assert i != -1
    trecho = fonte[i:i + 4000]

    assert 'return {**cached, "cache_hit": True}' not in trecho, (
        "o /query voltou a devolver o payload do cache sem sobrescrever os ids"
    )
    assert '"conversation_id": str(conv_id)' in trecho
    assert '"interaction_id": str(cached_interaction.id)' in trecho


def test_query_grava_interaction_no_cache_hit():
    """Sem Interaction, `vigilancia_service.medir_cache_semantico` fica cega
    para este caminho — ela conta hits por `Interaction.cache_hit`."""
    from app.services import orquestrador_service

    fonte = _fonte(orquestrador_service)
    i = fonte.find("if cached is not None:")
    trecho = fonte[i:i + 4000]

    assert "cache_hit=True" in trecho, "o /query não registra o hit no banco"
    assert "InteractionResponse(" in trecho


def test_os_dois_caminhos_tratam_o_cache_hit_igual():
    """A divergência que este bloco veio consertar."""
    from app.services import orquestrador_service, orquestrador_stream_service

    for modulo, nome in (
        (orquestrador_service, "/query"),
        (orquestrador_stream_service, "/stream"),
    ):
        fonte = _fonte(modulo)
        i = fonte.find("if cached is not None:")
        trecho = fonte[i:i + 4000]
        assert "ensure_conversation" in trecho, f"{nome} não cria conversa no hit"
        assert "cache_hit=True" in trecho, f"{nome} não grava o hit"
        assert "conversation_id" in trecho, f"{nome} não devolve id próprio"


# ── Cache não serve resposta condicionada a paciente ─────────────────────────

def test_contexto_com_evolucao_desliga_o_cache():
    """A chave do cache é `(modo, prompt)`, mas a resposta é gerada com a
    evolução da pasta junto. Servi-la a outro médico entregaria conduta
    calibrada para um paciente que não é o dele — vazamento e risco clínico."""
    from app.services.orquestrador_shared import contexto_tem_dado_de_paciente

    com_evolucao = [
        {"role": "user", "content": "[Evolução do paciente — informada pelo médico...] Jorge, DRC"},
        {"role": "user", "content": "qual anti-hipertensivo escolher?"},
    ]

    assert contexto_tem_dado_de_paciente(com_evolucao) is True


def test_contexto_com_trechos_da_pasta_desliga_o_cache():
    """Vale também para o material recuperado por similaridade: ele pode ser de
    outro paciente da mesma pasta."""
    from app.services.orquestrador_shared import contexto_tem_dado_de_paciente

    com_pasta = [
        {"role": "user", "content": "[Contexto de outras conversas desta pasta...] caso X"},
        {"role": "user", "content": "e agora?"},
    ]

    assert contexto_tem_dado_de_paciente(com_pasta) is True


def test_conversa_comum_continua_cacheavel():
    """A correção não pode matar o cache: pergunta genérica, sem pasta, segue
    valendo — que é justamente o caso em que o cache é seguro e útil."""
    from app.services.orquestrador_shared import contexto_tem_dado_de_paciente

    comum = [
        {"role": "user", "content": "qual a dose de amoxicilina para sinusite?"},
        {"role": "assistant", "content": "500mg 8/8h por 10 dias."},
    ]

    assert contexto_tem_dado_de_paciente(comum) is False
    assert contexto_tem_dado_de_paciente([]) is False


def test_os_dois_caminhos_aplicam_o_gate_na_leitura_e_na_gravacao():
    """Bloquear só a leitura não bastaria: a resposta condicionada entraria no
    cache e vazaria na próxima leitura de outro médico."""
    from app.services import orquestrador_service, orquestrador_stream_service

    for modulo, nome in (
        (orquestrador_service, "/query"),
        (orquestrador_stream_service, "/stream"),
    ):
        fonte = _fonte(modulo)
        # A CHAMADA, não o import: um `import` órfão continua no arquivo depois
        # de alguém remover a checagem, e o teste passaria por engano — foi o
        # que aconteceu na primeira versão deste teste.
        assert "not contexto_tem_dado_de_paciente(history_messages)" in fonte, (
            f"{nome} não checa o contexto de paciente antes de cachear"
        )
        # `pode_cachear` precisa aparecer três vezes: definição, gate da
        # leitura e gate da gravação.
        assert fonte.count("pode_cachear") >= 3, (
            f"{nome} não aplica o gate na leitura E na gravação"
        )
