"""
Contexto do usuário no prompt.

Antes, `_user_context_suffix` saía com string vazia sempre que não havia
especialidade — e como generalista e graduando NUNCA têm especialidade (nem o
onboarding perguntava, nem o grupo `[CFM]` existe para eles), esses dois perfis
eram os únicos que o produto tratava como anônimos. O modelo respondia a um
estudante de medicina exatamente como responderia a um cardiologista.
"""

from app.core.prompts import _user_context_suffix


def test_generalista_deixou_de_ser_anonimo():
    ctx = _user_context_suffix(None, "generalista")
    assert "generalista" in ctx
    assert "Calibre a profundidade" in ctx


def test_graduando_deixou_de_ser_anonimo():
    """É o perfil em que calibrar importa mais."""
    assert "estudante de medicina" in _user_context_suffix(None, "graduando")


def test_residente_com_especialidade_nao_e_chamado_de_especialista():
    """Ele está EM formação nela — a redação anterior se contradizia."""
    ctx = _user_context_suffix("Cardiologia", "residente")
    assert "residente em Cardiologia" in ctx
    assert "especialista em Cardiologia" not in ctx


def test_especialista_mantem_a_redacao():
    assert "especialista em Cardiologia" in _user_context_suffix("Cardiologia", "especialista")


def test_sem_nada_sabido_nao_inventa():
    """Usuário recém-criado pelo embed: sem especialidade e sem med_status.

    Aqui o silêncio é correto — supor um perfil seria pior do que não ter.
    """
    assert _user_context_suffix(None, None) == ""
    assert _user_context_suffix(None, "valor_estranho") == ""
