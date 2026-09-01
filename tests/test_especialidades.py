"""
Consistência do vocabulário canônico e da regra de precedência.

O teste mais importante daqui é `test_vocabulario_bate_com_a_lista_do_onboarding`:
ele prova que `app/medicina/especialidades.py` nasceu FIEL à lista que gerou os
valores hoje gravados em `users.specialty` e em `news.topic_specialties`. Se o
módulo divergisse do TSX, a migração silenciosamente deixaria de reconhecer a
especialidade de parte da base — sem erro, sem log.
"""

import re
from datetime import UTC, datetime

import pytest

from app.medicina import especialidades, identidade

# Os 55 rótulos exatamente como estavam no `OnboardingPage.tsx` quando o
# vocabulário nasceu — e, portanto, exatamente como estão gravados hoje em
# `users.specialty` e em `news.topic_specialties.specialty`.
#
# Congelado aqui de propósito. Antes o teste LIA o TSX com regex, porque a lista
# só existia lá; agora que ela mora no backend, ler o TSX não provaria nada (os
# dois sairiam da mesma fonte). O que ainda precisa de proteção é outra coisa:
# renomear um rótulo é uma MIGRAÇÃO DE DADOS, não uma edição de texto. Mudar
# "Clínica Médica" aqui sem migrar as duas tabelas faz o feed de notícias parar
# de casar — em silêncio, para todos os clínicos.
ROTULOS_EM_PRODUCAO = {
    "Acupuntura", "Alergia e Imunologia", "Anestesiologia", "Angiologia",
    "Cardiologia", "Cirurgia Cardiovascular", "Cirurgia da Mão",
    "Cirurgia de Cabeça e Pescoço", "Cirurgia do Aparelho Digestivo",
    "Cirurgia Geral", "Cirurgia Oncológica", "Cirurgia Pediátrica",
    "Cirurgia Plástica", "Cirurgia Torácica", "Cirurgia Vascular",
    "Clínica Médica", "Coloproctologia", "Dermatologia",
    "Endocrinologia e Metabologia", "Endoscopia", "Gastroenterologia",
    "Genética Médica", "Geriatria", "Ginecologia e Obstetrícia",
    "Hematologia e Hemoterapia", "Homeopatia", "Infectologia", "Mastologia",
    "Medicina de Emergência", "Medicina de Família e Comunidade",
    "Medicina do Esporte", "Medicina do Trabalho", "Medicina do Tráfego",
    "Medicina Física e Reabilitação", "Medicina Intensiva",
    "Medicina Legal e Perícia Médica", "Medicina Nuclear",
    "Medicina Preventiva e Social", "Nefrologia", "Neurocirurgia",
    "Neurologia", "Nutrologia", "Oftalmologia", "Oncologia Clínica",
    "Ortopedia e Traumatologia", "Otorrinolaringologia", "Patologia",
    "Patologia Clínica/Medicina Laboratorial", "Pediatria", "Pneumologia",
    "Psiquiatria", "Radiologia e Diagnóstico por Imagem", "Radioterapia",
    "Reumatologia", "Urologia",
}


# ── Vocabulário ───────────────────────────────────────────────────────────

def test_rotulos_em_producao_nao_mudam_sem_migracao():
    """Acrescentar especialidade é livre; RENOMEAR exige migrar os dados.

    Se este teste falhar porque um rótulo sumiu ou mudou, a pergunta não é "como
    conserto o teste" — é "quem vai atualizar `users.specialty` e
    `news.topic_specialties.specialty` das linhas que já existem".
    """
    assert ROTULOS_EM_PRODUCAO <= especialidades.nomes_canonicos()


def test_a_lista_do_tsx_foi_embora():
    """A lista era hardcoded no front e servida de lá para o backend inteiro.

    Guarda contra reintrodução: se alguém colar as especialidades de volta num
    componente, volta a haver duas fontes divergentes — que é o defeito que este
    módulo veio corrigir.
    """
    from pathlib import Path

    tsx = Path(__file__).resolve().parents[1] / "frontend-app/src/pages/OnboardingPage.tsx"
    assert "const ESPECIALIDADES" not in tsx.read_text(encoding="utf-8")


def test_slugs_sao_unicos_e_kebab():
    slugs = [e.slug for e in especialidades.ESPECIALIDADES]
    assert len(slugs) == len(set(slugs))
    for slug in slugs:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug), slug


def test_nomes_sao_unicos():
    nomes = [e.nome for e in especialidades.ESPECIALIDADES]
    assert len(nomes) == len(set(nomes))


def test_normalizar_ignora_acento_caixa_e_espaco():
    assert especialidades.normalizar("Cardiologia") == "cardiologia"
    assert especialidades.normalizar("  cardiologia ") == "cardiologia"
    assert especialidades.normalizar("CLINICA MEDICA") == "clinica-medica"
    assert especialidades.normalizar("Clínica Médica") == "clinica-medica"


def test_normalizar_resolve_os_nomes_curtos_do_detector():
    """Os 31 nomes do `specialty_detector` eram vocabulário incompatível.

    Enquanto não resolviam, `interactions.specialty_detected` e `users.specialty`
    guardavam grafias diferentes da mesma coisa — qualquer cruzamento dos dois
    dava resultado errado sem parecer errado.
    """
    assert especialidades.normalizar("Ortopedia") == "ortopedia-e-traumatologia"
    assert especialidades.normalizar("Endocrinologia") == "endocrinologia-e-metabologia"
    assert especialidades.normalizar("Clínica Geral") == "clinica-medica"
    assert especialidades.normalizar("Cirurgia") == "cirurgia-geral"
    assert especialidades.normalizar("Ginecologia") == "ginecologia-e-obstetricia"
    assert especialidades.normalizar("Obstetrícia") == "ginecologia-e-obstetricia"
    assert especialidades.normalizar("Oncologia") == "oncologia-clinica"
    assert especialidades.normalizar("Radiologia") == "radiologia-e-diagnostico-por-imagem"
    assert especialidades.normalizar("Medicina Esportiva") == "medicina-do-esporte"


def test_normalizar_nao_adivinha():
    """Sem fuzzy match: palpite errado grava especialidade errada em silêncio."""
    assert especialidades.normalizar("Cardio") is None
    assert especialidades.normalizar("Especialista em coração") is None
    assert especialidades.normalizar("") is None
    assert especialidades.normalizar(None) is None


def test_normalizar_e_idempotente():
    for esp in especialidades.ESPECIALIDADES:
        assert especialidades.normalizar(esp.slug) == esp.slug
        assert especialidades.normalizar(esp.nome) == esp.slug


def test_generalista_existe_no_vocabulario():
    """O piso do feed de notícias precisa ser um slug real."""
    assert especialidades.por_slug(especialidades.ESPECIALIDADE_GENERALISTA) is not None


def test_detector_e_subconjunto():
    nomes = set(especialidades.nomes_para_detector())
    assert nomes and nomes <= especialidades.nomes_canonicos()


# ── Grupos da WAID ────────────────────────────────────────────────────────

def test_grupos_reais_do_painel_resolvem_sem_alias():
    """Os quatro nomes do print do painel, exatamente como chegam.

    Caixa alta e acento não precisam de alias — a comparação já os ignora.
    """
    for nome, esperado in [
        ("[CFM] NEUROLOGIA", "neurologia"),
        ("[CFM] DERMATOLOGIA", "dermatologia"),
        ("[CFM] CLÍNICA MÉDICA", "clinica-medica"),
        ("[CFM] CARDIOLOGIA", "cardiologia"),
        ("[CFM] Alergia e Imunologia", "alergia-e-imunologia"),
    ]:
        grupo = especialidades.de_grupo_cfm(nome)
        assert grupo is not None and grupo.slug == esperado, nome


def test_grupo_sem_prefixo_nao_e_de_especialidade():
    """O membro está em vários grupos: turma, produto, campanha."""
    assert especialidades.de_grupo_cfm("Turma 2026") is None
    assert especialidades.de_grupo_cfm("Assinantes Premium") is None
    assert especialidades.de_grupo_cfm("") is None
    assert especialidades.de_grupo_cfm(None) is None


def test_grupo_de_especialidade_nao_reconhecida_preserva_o_rotulo():
    """O caso da ÁREA DE ATUAÇÃO — o alarme, não o silêncio.

    Os grupos nascem automaticamente; se o CFM devolver "Hepatologia" (área de
    atuação, não especialidade), o grupo é criado e não casa com as 55. Tem que
    ser distinguível de "não é grupo de especialidade".
    """
    grupo = especialidades.de_grupo_cfm("[CFM] Hepatologia")
    assert grupo is not None
    assert grupo.slug is None
    assert grupo.rotulo == "Hepatologia"


def test_duas_residencias_guarda_as_duas():
    """O caso comum: Clínica Médica é pré-requisito de quase toda residência.

    Guardar só uma revogaria em silêncio o acesso à outra, já que a
    especialidade vai definir acesso a conteúdo pago.
    """
    r = especialidades.interpretar_grupos(
        ["Turma 2026", "[CFM] CLÍNICA MÉDICA", "[CFM] CARDIOLOGIA"]
    )
    assert set(r.slugs) == {"clinica-medica", "cardiologia"}


def test_pre_requisito_perde_para_a_especialidade_exercida():
    """Um cardiologista não pode virar clínico geral por ordem de lista."""
    r = especialidades.interpretar_grupos(["[CFM] CLÍNICA MÉDICA", "[CFM] CARDIOLOGIA"])
    assert r.principal == "cardiologia"
    # E a ordem inversa dá o mesmo resultado — é regra, não sorteio.
    invertido = especialidades.interpretar_grupos(
        ["[CFM] CARDIOLOGIA", "[CFM] CLÍNICA MÉDICA"]
    )
    assert invertido.principal == "cardiologia"


def test_cirurgia_geral_tambem_e_pre_requisito():
    r = especialidades.interpretar_grupos(
        ["[CFM] CIRURGIA GERAL", "[CFM] CIRURGIA VASCULAR"]
    )
    assert r.principal == "cirurgia-vascular"


def test_so_pre_requisito_continua_valendo():
    """Clínico geral de verdade não pode ficar sem especialidade."""
    r = especialidades.interpretar_grupos(["[CFM] CLÍNICA MÉDICA"])
    assert r.principal == "clinica-medica"


def test_empate_sem_criterio_e_deterministico():
    """Sem vencedor natural, desempata alfabeticamente — o que importa é não
    mudar sozinho entre um login e outro. O feed usa a lista inteira mesmo."""
    a = especialidades.interpretar_grupos(
        ["[CFM] MEDICINA INTENSIVA", "[CFM] CARDIOLOGIA"]
    )
    b = especialidades.interpretar_grupos(
        ["[CFM] CARDIOLOGIA", "[CFM] MEDICINA INTENSIVA"]
    )
    assert a.principal == b.principal == "cardiologia"


def test_generalista_e_rotulo_conhecido_e_nao_lacuna():
    """`[CFM] GENERALISTA`: o CFM foi consultado e não devolveu especialidade."""
    r = especialidades.interpretar_grupos(["[CFM] GENERALISTA"])
    assert r.generalista is True
    assert r.slugs == ()
    assert r.desconhecidos == ()  # não é lacuna da taxonomia
    assert r.principal is None


def test_generalista_nao_vira_clinica_medica():
    """Clínica Médica é especialidade real, com RQE.

    Mapear "GENERALISTA" para ela afirmaria um registro que o Conselho diz não
    existir — num campo que tem proveniência e vai definir acesso pago. O
    conteúdo do generalista é resolvido noutra camada (`ESPECIALIDADE_PISO`).
    """
    assert especialidades.normalizar("GENERALISTA") is None


def test_generalista_convive_com_especialidade_de_verdade():
    """Se houver as duas coisas, a especialidade é que vale."""
    r = especialidades.interpretar_grupos(["[CFM] GENERALISTA", "[CFM] CARDIOLOGIA"])
    assert r.generalista is True
    assert r.principal == "cardiologia"


def test_desconhecido_nao_contamina_os_reconhecidos():
    r = especialidades.interpretar_grupos(["[CFM] Hepatologia", "[CFM] Cardiologia"])
    assert r.slugs == ("cardiologia",)
    assert r.desconhecidos == ("Hepatologia",)


def test_sem_grupo_de_especialidade():
    for entrada in (["Turma 2026"], [], None):
        r = especialidades.interpretar_grupos(entrada)
        assert r.slugs == () and r.principal is None


# ── Precedência ───────────────────────────────────────────────────────────

class UsuarioFake:
    """Só os atributos que `identidade` toca — não precisa de banco."""

    def __init__(self, **kw):
        self.name = kw.get("name")
        self.crm = kw.get("crm")
        self.med_status = kw.get("med_status")
        self.specialty = kw.get("specialty")
        self.specialty_slug = kw.get("specialty_slug")
        self.specialties = kw.get("specialties")
        self.specialty_source = kw.get("specialty_source")
        self.specialty_rqe = kw.get("specialty_rqe")
        self.specialty_updated_at = kw.get("specialty_updated_at")
        self.crm_verified_at = kw.get("crm_verified_at")


def test_cadastro_sobrescreve_o_que_o_medico_digitou():
    """`declarado` é fallback, não verdade.

    O médico da base antiga digitou uma especialidade porque não havia fonte
    melhor. Quando o cadastro real chega pelo webhook, ele manda — o campo é
    identidade profissional e vai definir acesso a conteúdo pago.
    """
    user = UsuarioFake(
        specialty="Nefrologia",
        specialty_slug="nefrologia",
        specialty_source=identidade.FONTE_DECLARADO,
    )
    assert identidade.aplicar_especialidade(
        user, slug="cardiologia", fonte=identidade.FONTE_CADASTRO
    )
    assert user.specialty_slug == "cardiologia"
    assert user.specialty == "Cardiologia"
    assert user.specialty_source == identidade.FONTE_CADASTRO


def test_grupo_da_waid_nao_desfaz_o_cadastro():
    """A reconciliação do login é a fonte mais fraca das automáticas.

    O nome do grupo é artefato de controle de acesso e pode ser renomeado no
    painel; o webhook do cadastro é o registro real. Sem esta ordem, um rename
    de grupo reescreveria a especialidade de todo mundo naquele grupo.
    """
    user = UsuarioFake(
        specialty_slug="cardiologia", specialty_source=identidade.FONTE_CADASTRO
    )
    assert not identidade.aplicar_especialidade(
        user, slug="nefrologia", fonte=identidade.FONTE_WAID_GRUPO
    )
    assert user.specialty_slug == "cardiologia"


def test_aplicar_guarda_a_lista_e_deriva_a_principal():
    user = UsuarioFake()
    assert identidade.aplicar_especialidade(
        user,
        slugs=["clinica-medica", "cardiologia"],
        fonte=identidade.FONTE_WAID_GRUPO,
    )
    assert user.specialties == ["cardiologia", "clinica-medica"]  # ordenada
    assert user.specialty_slug == "cardiologia"  # pré-requisito não vence
    assert user.specialty == "Cardiologia"


def test_aplicar_com_uma_so_preenche_a_lista_tambem():
    user = UsuarioFake()
    identidade.aplicar_especialidade(
        user, slug="pediatria", fonte=identidade.FONTE_CADASTRO
    )
    assert user.specialties == ["pediatria"]


def test_reordenar_a_mesma_lista_nao_e_mudanca():
    """A API externa não garante ordem; sem isto todo login viraria um UPDATE."""
    user = UsuarioFake()
    identidade.aplicar_especialidade(
        user, slugs=["cardiologia", "clinica-medica"], fonte=identidade.FONTE_WAID_GRUPO
    )
    assert not identidade.aplicar_especialidade(
        user, slugs=["clinica-medica", "cardiologia"], fonte=identidade.FONTE_WAID_GRUPO
    )


def test_admin_ganha_de_tudo():
    """A correção do suporte não pode ser desfeita pelo próximo login."""
    user = UsuarioFake(
        specialty_slug="cardiologia", specialty_source=identidade.FONTE_CADASTRO
    )
    assert identidade.aplicar_especialidade(
        user, slug="nefrologia", fonte=identidade.FONTE_ADMIN
    )
    assert not identidade.aplicar_especialidade(
        user, slug="pediatria", fonte=identidade.FONTE_CADASTRO
    )
    assert user.specialty_slug == "nefrologia"


def test_campo_vazio_aceita_qualquer_fonte():
    user = UsuarioFake()
    assert identidade.aplicar_especialidade(
        user, slug="pediatria", fonte=identidade.FONTE_WAID_GRUPO
    )
    assert user.specialty_slug == "pediatria"
    assert user.specialty_updated_at is not None


def test_reaplicar_o_mesmo_valor_nao_e_mudanca():
    """Idempotência: é o que torna seguro reenviar o mesmo webhook."""
    user = UsuarioFake()
    agora = datetime(2026, 1, 1, tzinfo=UTC)
    assert identidade.aplicar_especialidade(
        user, slug="pediatria", fonte=identidade.FONTE_CADASTRO, agora=agora
    )
    assert not identidade.aplicar_especialidade(
        user, slug="pediatria", fonte=identidade.FONTE_CADASTRO
    )
    assert user.specialty_updated_at == agora  # não foi tocado de novo


def test_escrita_de_outra_fonte_zera_o_rqe():
    """Só o CFM confere registro — ninguém mais herda o selo de verificado."""
    user = UsuarioFake(
        specialty_slug="cardiologia",
        specialty_source=identidade.FONTE_CFM,
        specialty_rqe="12345",
    )
    assert identidade.aplicar_especialidade(
        user, slug="nefrologia", fonte=identidade.FONTE_CADASTRO
    )
    assert user.specialty_rqe is None


def test_cadastro_ganha_do_cfm():
    """O RQE prova o registro; o acesso vem do que foi contratado."""
    user = UsuarioFake(specialty_slug="nefrologia", specialty_source=identidade.FONTE_CFM)
    assert identidade.aplicar_especialidade(
        user, slug="cardiologia", fonte=identidade.FONTE_CADASTRO
    )


# ── Trava de edição ───────────────────────────────────────────────────────

def test_medico_edita_so_o_que_ele_mesmo_digitou():
    assert identidade.usuario_pode_editar(UsuarioFake())
    assert identidade.usuario_pode_editar(
        UsuarioFake(specialty_source=identidade.FONTE_DECLARADO)
    )


def test_fonte_automatica_tranca_a_edicao():
    """Sem isto, trocar de especialidade viraria caminho para alcançar conteúdo
    de outro produto — o grupo da WAID é grupo de ACESSO."""
    for fonte in (
        identidade.FONTE_CADASTRO,
        identidade.FONTE_WAID_GRUPO,
        identidade.FONTE_CFM,
        identidade.FONTE_ADMIN,
    ):
        assert not identidade.usuario_pode_editar(UsuarioFake(specialty_source=fonte)), fonte


def test_fonte_ou_slug_invalido_explode():
    user = UsuarioFake()
    with pytest.raises(ValueError):
        identidade.aplicar_especialidade(user, slug="cardiologia", fonte="chute")
    with pytest.raises(ValueError):
        identidade.aplicar_especialidade(
            user, slug="cardio", fonte=identidade.FONTE_DECLARADO
        )


# ── Pendências ────────────────────────────────────────────────────────────

def test_graduando_nao_deve_crm_nem_especialidade():
    """Sem esta guarda o aluno fica preso pedindo um registro que não tem."""
    user = UsuarioFake(name="Ana", med_status="graduando")
    assert identidade.pendencias(user, aceite_vigente=True) == []


def test_generalista_sem_especialidade_esta_completo():
    user = UsuarioFake(name="Ana", med_status="generalista", crm="123456")
    assert identidade.pendencias(user, aceite_vigente=True) == []


def test_especialista_sem_especialidade_tem_pendencia():
    user = UsuarioFake(name="Ana", med_status="especialista", crm="123456")
    assert identidade.pendencias(user, aceite_vigente=True) == ["especialidade"]


def test_usuario_de_embed_so_com_email():
    """O caso real: `get_or_create_embed_user` cria com e-mail e mais nada.

    Sem `med_status` não se cobra CRM nem especialidade ainda — não dá para
    saber se a pessoa é graduanda. Uma pergunta de cada vez.
    """
    user = UsuarioFake()
    assert identidade.pendencias(user, aceite_vigente=False) == [
        "aceite_termos",
        "nome",
        "med_status",
    ]


def test_endpoint_publico_serve_o_vocabulario_inteiro():
    """A lista tem que sair do TSX por algum lugar — este é o lugar."""
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async def _chamar():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            return await c.get("/api/v1/meta/especialidades")

    resp = asyncio.run(_chamar())
    assert resp.status_code == 200
    corpo = resp.json()
    assert {e["nome"] for e in corpo} == especialidades.nomes_canonicos()
    assert corpo == sorted(corpo, key=lambda e: e["nome"])


def test_aceite_e_pendencia_mesmo_com_perfil_cheio():
    """A armadilha da LGPD: perfil completo não é prova de consentimento."""
    user = UsuarioFake(
        name="Ana",
        med_status="especialista",
        crm="123456",
        specialty_slug="cardiologia",
    )
    assert identidade.pendencias(user, aceite_vigente=False) == ["aceite_termos"]
    assert identidade.perfil_completo(user, aceite_vigente=True)


# ── Opções de carreira derivadas ──────────────────────────────────────────

def test_com_especialidade_registrada_nao_oferece_graduando_nem_generalista():
    """A queixa do Rúben: por que ofereço 'aluno de graduação' a quem está em
    `[CFM] Cardiologia`? Estar no grupo prova que há CRM e há RQE."""
    user = UsuarioFake(
        specialty_slug="cardiologia", specialty_source=identidade.FONTE_WAID_GRUPO
    )
    assert identidade.med_status_possiveis(user) == ["residente", "especialista"]


def test_crm_verificado_sem_especialidade_sobra_generalista_ou_residente():
    """`[CFM] GENERALISTA`: o Conselho tem o CRM e nenhuma especialidade.

    Não é graduando (tem registro) nem especialista (não tem RQE). Mas pode ser
    um R1, que ainda não tem RQE — por isso são duas opções, não uma.
    """
    user = UsuarioFake(crm_verified_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert identidade.med_status_possiveis(user) == ["generalista", "residente"]


def test_sem_nada_verificado_oferece_os_quatro():
    assert identidade.med_status_possiveis(UsuarioFake()) == list(identidade.MED_STATUS_TODOS)


def test_especialidade_declarada_nao_restringe():
    """Só fonte que passou pelo CFM prova CRM. O que o médico digitou, não."""
    user = UsuarioFake(
        specialty_slug="cardiologia", specialty_source=identidade.FONTE_DECLARADO
    )
    assert identidade.med_status_possiveis(user) == list(identidade.MED_STATUS_TODOS)
