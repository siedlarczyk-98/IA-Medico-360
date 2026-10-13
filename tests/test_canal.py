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


@pytest.mark.parametrize(("grupos", "porta"), [
    (["[Cursos Active] Médico(a) - ACLS"], "cursos_active"),
    (["[CFM] CARDIOLOGIA"], "cadastro_cfm"),
    (["[CFM] CARDIOLOGIA", "[Cursos Active] Médico(a) - ACLS"], "cursos_active"),
    (["Pfizer | Speakers"], None),
    ([], None),
])
def test_canal_de_entrada(grupos, porta):
    assert canal.canal_de_entrada(grupos) == porta


def test_grupos_do_medico360_filtra_e_ordena():
    assert canal.grupos_do_medico360([
        "Turma 2026", "[CFM] PEDIATRIA", "[Cursos Active] Médico(a) - ACLS", "[CFM] PEDIATRIA",
    ]) == ["[CFM] PEDIATRIA", "[Cursos Active] Médico(a) - ACLS"]
