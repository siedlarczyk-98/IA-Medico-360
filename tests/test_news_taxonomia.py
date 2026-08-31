"""
Consistência da taxonomia de temas.

Nenhum destes testes precisa de banco: a taxonomia é dado estático, e os defeitos
que ela pode ter são de coerência interna. Eles rodam rápido e pegam a classe de
erro mais provável — alguém acrescenta um tema e digita a especialidade errado,
o que faz o tema simplesmente nunca aparecer para ninguém, em silêncio.
"""

import re
from pathlib import Path

import pytest

from app.news.taxonomia import CORE, RELEVANTE, TAXONOMIA, especialidades_citadas, slugs

ONBOARDING_TSX = Path(__file__).resolve().parents[1] / "frontend-app/src/pages/OnboardingPage.tsx"


def _especialidades_do_onboarding() -> set[str]:
    """
    Lê a lista de especialidades da tela de onboarding.

    Ler do TSX em vez de duplicar a lista aqui é o ponto do teste: `users.specialty`
    guarda exatamente o texto que aquela tela oferece, então é contra ELA que a
    taxonomia precisa bater. Uma cópia neste arquivo envelheceria em silêncio e o
    teste passaria a garantir nada.
    """
    fonte = ONBOARDING_TSX.read_text(encoding="utf-8")
    bloco = re.search(r"const ESPECIALIDADES = \[(.*?)\];", fonte, re.S)
    assert bloco, "Não encontrei ESPECIALIDADES em OnboardingPage.tsx"
    return set(re.findall(r"'([^']+)'", bloco.group(1)))


def test_slugs_sao_unicos():
    todos = [t["slug"] for t in TAXONOMIA]
    assert len(todos) == len(set(todos)), "Há slug repetido na taxonomia"


def test_slugs_sao_kebab_case():
    # O slug vai para a URL e para a resposta da API; espaço ou maiúscula ali
    # vira bug de encoding em algum ponto do caminho.
    for slug in slugs():
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug), f"slug inválido: {slug}"


def test_todo_tema_tem_ao_menos_uma_especialidade():
    for tema in TAXONOMIA:
        assert tema["especialidades"], f"Tema sem especialidade: {tema['slug']}"


def test_todo_tema_tem_ao_menos_um_core():
    """
    Tema sem nenhum `core` não é pré-marcado como prioridade para ninguém e
    tende a ficar órfão na tela de escolha.
    """
    for tema in TAXONOMIA:
        pesos = {peso for _, peso in tema["especialidades"]}
        assert CORE in pesos, f"Tema sem especialidade 'core': {tema['slug']}"


def test_pesos_sao_validos():
    for tema in TAXONOMIA:
        for especialidade, peso in tema["especialidades"]:
            assert peso in (CORE, RELEVANTE), f"peso inválido em {tema['slug']}: {peso}"


def test_nao_ha_especialidade_repetida_no_mesmo_tema():
    for tema in TAXONOMIA:
        nomes = [esp for esp, _ in tema["especialidades"]]
        assert len(nomes) == len(set(nomes)), f"Especialidade repetida em {tema['slug']}"


def test_especialidades_existem_no_onboarding():
    """
    O teste mais importante deste arquivo.

    `users.specialty` guarda o texto exato escolhido na tela de onboarding. Uma
    especialidade escrita de forma diferente aqui (ex: "Endocrinologia" em vez de
    "Endocrinologia e Metabologia") nunca casaria com nenhum usuário — e o modo
    de falha é silencioso: o tema simplesmente não é sugerido a ninguém, sem
    erro, sem log, sem nada.
    """
    validas = _especialidades_do_onboarding()
    invalidas = especialidades_citadas() - validas
    assert not invalidas, (
        f"Especialidades que não existem no onboarding: {sorted(invalidas)}. "
        "Elas nunca casariam com nenhum usuário."
    )


@pytest.mark.parametrize(
    "slug,esperadas",
    [
        # O caso que motivou o desenho inteiro: um cardiologista PRECISA receber
        # conteúdo de obesidade, e um endocrinologista também, sem que exista
        # nenhum caso especial em código sobre obesidade.
        ("obesidade", {"Cardiologia", "Endocrinologia e Metabologia", "Nutrologia"}),
        # Anticoagulação atravessa cardio, pneumo e hemato.
        ("anticoagulacao", {"Cardiologia", "Pneumologia", "Hematologia e Hemoterapia"}),
    ],
)
def test_temas_transversais_alcancam_varias_especialidades(slug, esperadas):
    tema = next(t for t in TAXONOMIA if t["slug"] == slug)
    presentes = {esp for esp, _ in tema["especialidades"]}
    assert esperadas <= presentes, (
        f"Tema transversal {slug} não alcança {sorted(esperadas - presentes)}"
    )


def test_infecto_e_cardio_nao_compartilham_temas_core():
    """
    A queixa literal do chefe: "se eu sou cardio, não deveria ser impactado com
    notícias de infecto". Compartilhar um tema `relevante` é legítimo (sepse
    interessa a quem faz UTI); compartilhar `core` significaria que o filtro não
    separa as duas especialidades em nada.
    """
    def cores(especialidade: str) -> set[str]:
        return {
            t["slug"]
            for t in TAXONOMIA
            if (especialidade, CORE) in [(e, p) for e, p in t["especialidades"]]
        }

    assert not (cores("Cardiologia") & cores("Infectologia"))


def test_piso_generalista_nao_fica_vazio():
    """
    `news_feed_service.ESPECIALIDADE_PISO` e o que sugere temas a quem ainda nao
    tem especialidade (usuario recem-criado pelo SSO de embed). Se ninguem citar
    essa especialidade na taxonomia, esse usuario recebe lista vazia — e o
    defeito e silencioso, porque nenhuma outra coisa quebra.
    """
    from app.services.news_feed_service import ESPECIALIDADE_PISO

    ligados = [
        t["slug"]
        for t in TAXONOMIA
        if any(esp == ESPECIALIDADE_PISO for esp, _ in t["especialidades"])
    ]
    assert len(ligados) >= 10, (
        f"Apenas {len(ligados)} tema(s) ligados a '{ESPECIALIDADE_PISO}'. "
        "Quem nao tem especialidade cairia numa lista quase vazia."
    )
