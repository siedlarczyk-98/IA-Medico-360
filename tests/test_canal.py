"""Leitura dos grupos da Waid: canal de entrada e profissão (app/medicina/canal.py)."""

import pytest

from app.medicina import canal


@pytest.mark.parametrize(("grupo", "profissao"), [
    ("[Cursos Active] Médico(a) - ACLS", "medico"),
    ("[Cursos Active] Médico(a) - ATHEROS", "medico"),
    ("[Cursos Active] Estudante 6º Medicina - RC", "estudante_medicina"),
    ("[Cursos Active] Enfermeiro(a) - PALS", "enfermeiro"),
    ("[Cursos Active] Estudantes 5º Enfermagem - ACLS", "estudante_enfermagem"),
    ("[Cursos Active] Profissionais de saúde - BLS", "profissional_saude"),
    ("[CFM] CARDIOLOGIA", "medico"),
    ("[CFM] GENERALISTA", "medico"),
    ("[ONBOARDING] - Médico(a)", "medico"),
    ("[ONBOARDING] - Estudante", "estudante_medicina"),
    ("[ONBOARDING] - Aluno Graduação Medicina", "estudante_medicina"),
    ("[ONBOARDING] - Enfermeiro(a)", "enfermeiro"),
    ("[ONBOARDING] - Profissionais de Saúde", "profissional_saude"),
    ("[cursos active]   MÉDICO(A) - acls", "medico"),
    ("Pfizer | Speakers | Cardiologia", None),
    ("[Cursos Active] Turma nova - ACLS", None),
])
def test_profissao_de_cada_grupo(grupo, profissao):
    assert canal.profissao([grupo]) == profissao


def test_estudante_que_se_formou_vale_medico():
    assert canal.profissao([
        "[Cursos Active] Estudante 6º Medicina - ACLS",
        "[Cursos Active] Médico(a) - PALS",
    ]) == "medico"


def test_bls_generico_perde_para_o_especifico():
    assert canal.profissao([
        "[Cursos Active] Profissionais de saúde - BLS",
        "[Cursos Active] Enfermeiro(a) - ACLS",
    ]) == "enfermeiro"


@pytest.mark.parametrize(("grupos", "farmaceutica", "porta"), [
    (["[Cursos Active] Médico(a) - ACLS"], False, "cursos_active"),
    # Cursos Active ganha mesmo de quem também está num andar de farmacêutica.
    (["[Cursos Active] Médico(a) - ACLS"], True, "cursos_active"),
    (["[CFM] CARDIOLOGIA"], False, "lp_medico360"),
    (["[ONBOARDING] - Estudante"], False, "lp_medico360"),
    (["[CFM] CARDIOLOGIA"], True, "immerso"),
    (["[ONBOARDING] - Médico(a)"], True, "immerso"),
    (["[CFM] CARDIOLOGIA", "[Cursos Active] Médico(a) - ACLS"], True, "cursos_active"),
    # Só andar de farmacêutica, sem nenhum dos três grupos: não conta.
    (["Pfizer | Speakers"], True, None),
    ([], False, None),
])
def test_canal_de_entrada(grupos, farmaceutica, porta):
    assert canal.canal_de_entrada(grupos, em_andar_de_farmaceutica=farmaceutica) == porta


def test_grupos_do_medico360_filtra_e_ordena():
    assert canal.grupos_do_medico360([
        "Turma 2026", "[CFM] PEDIATRIA", "[Cursos Active] Médico(a) - ACLS", "[CFM] PEDIATRIA",
        "[ONBOARDING] - Estudante", "[Pfizer] ST-ATTRs",
    ]) == ["[CFM] PEDIATRIA", "[Cursos Active] Médico(a) - ACLS", "[ONBOARDING] - Estudante"]


@pytest.mark.parametrize(("andar", "e_farma"), [
    ({"uuid": "60f3263a-f1a7-4cc8-b8d8-3e48597d1b1e", "name": "Pfizer"}, True),
    ({"uuid": "d1fce8b6-2b39-4009-bc97-581bf73cd157", "name": "Lilly"}, True),
    # Médico 360, Área de parceiros, Aplicativo e SBC não são farmacêutica.
    ({"uuid": "4037b710-50c5-11ed-b97b-16058182e383", "name": "Médico 360"}, False),
    ({"uuid": "e03a1aa1-1e8b-4636-b2a0-f7f1fd79f522", "name": "SBC"}, False),
    ({"name": "Pfizer"}, False),  # sem uuid não dá para afirmar
    (None, False),
])
def test_andar_de_farmaceutica(andar, e_farma):
    assert canal.e_andar_de_farmaceutica(andar) is e_farma
