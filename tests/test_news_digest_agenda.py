"""
Testes da agenda do digest: quando cada médico recebe.

Funções puras, sem banco e sem relógio real — dá para percorrer a semana
inteira, hora a hora, e afirmar exatamente quantas vezes cada agenda dispara.
É o que importa num agendador: não "funcionou uma vez", e sim "dispara UMA vez
por período, e nas outras 167 horas fica quieto".
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services import news_digest_agenda as ag

# Segunda-feira, 2026-09-21, meia-noite UTC.
SEGUNDA = datetime(2026, 9, 21, 0, 0, tzinfo=UTC)
assert SEGUNDA.weekday() == 0


def horas_da_semana(inicio=SEGUNDA, quantas=24 * 7):
    return [inicio + timedelta(hours=h) for h in range(quantas)]


def disparos(agenda, horas=None):
    horas = horas if horas is not None else horas_da_semana()
    return [t for t in horas if ag.esta_na_hora(agenda, t)]


# ── conversão de faixa ───────────────────────────────────────────────────────

@pytest.mark.parametrize(("faixa", "hora_brt"), [("manha", 7), ("tarde", 13), ("noite", 19)])
def test_faixa_vira_hora_utc_somando_tres(faixa, hora_brt):
    """Brasília é UTC-3: 7h BRT é 10h UTC."""
    assert ag.hora_utc_da_faixa(faixa) == hora_brt + 3


def test_faixa_desconhecida_cai_na_manha():
    assert ag.hora_utc_da_faixa("madrugada") == ag.hora_utc_da_faixa("manha")


# ── diário ───────────────────────────────────────────────────────────────────

def test_diario_dispara_uma_vez_por_dia():
    d = disparos({"frequencia": "diario", "faixa": "manha"})
    assert len(d) == 7
    assert {t.hour for t in d} == {10}
    assert sorted(t.weekday() for t in d) == [0, 1, 2, 3, 4, 5, 6]


def test_diario_respeita_a_faixa_escolhida():
    assert {t.hour for t in disparos({"frequencia": "diario", "faixa": "tarde"})} == {16}
    assert {t.hour for t in disparos({"frequencia": "diario", "faixa": "noite"})} == {22}


# ── semanal ──────────────────────────────────────────────────────────────────

def test_semanal_dispara_uma_unica_vez_na_semana():
    d = disparos({"frequencia": "semanal", "dia_semana": 2, "faixa": "manha"})
    assert len(d) == 1
    assert d[0].weekday() == 2
    assert d[0].hour == 10


@pytest.mark.parametrize("dia", [0, 1, 2, 3, 4, 5, 6])
def test_semanal_acerta_qualquer_dia_escolhido(dia):
    d = disparos({"frequencia": "semanal", "dia_semana": dia, "faixa": "tarde"})
    assert len(d) == 1
    assert d[0].weekday() == dia


def test_semanal_conta_o_dia_em_brasilia_nao_em_utc():
    """A faixa da noite (19h BRT) é 22h UTC — mesmo dia nos dois. Mas se um dia
    existir faixa que cruze a meia-noite UTC, o dia da semana divergiria; a
    conversão antes de comparar é o que mantém a regra certa."""
    # 22h UTC de segunda ainda é segunda em Brasília (19h).
    t = datetime(2026, 9, 21, 22, tzinfo=UTC)
    assert ag.esta_na_hora({"frequencia": "semanal", "dia_semana": 0, "faixa": "noite"}, t)
    # E a terça 22h UTC não dispara a agenda de segunda.
    assert not ag.esta_na_hora(
        {"frequencia": "semanal", "dia_semana": 0, "faixa": "noite"},
        datetime(2026, 9, 22, 22, tzinfo=UTC),
    )


# ── normalização: o JSONB aceita qualquer coisa ──────────────────────────────

def test_agenda_ausente_mantem_o_comportamento_antigo():
    """Quem nunca escolheu nada continua diário, de manhã. Ninguém muda de
    horário por efeito colateral de um deploy nosso."""
    assert ag.normalizar(None) == {"frequencia": "diario", "dia_semana": 0, "faixa": "manha"}
    assert ag.normalizar({}) == ag.normalizar(None)


@pytest.mark.parametrize("lixo", [
    {"frequencia": "mensal"},
    {"frequencia": 7},
    {"faixa": "madrugada"},
    {"faixa": None},
    {"dia_semana": 9},
    {"dia_semana": -1},
    {"dia_semana": "segunda"},
    {"dia_semana": 1.5},
])
def test_valor_invalido_vira_padrao_em_vez_de_explodir(lixo):
    """Uma agenda inválida NÃO pode virar exceção: derrubaria o digest de todo
    mundo por causa da preferência de uma pessoa."""
    a = ag.normalizar(lixo)
    assert a["frequencia"] in ag.FREQUENCIAS
    assert a["faixa"] in ag.FAIXAS
    assert 0 <= a["dia_semana"] <= 6


def test_true_nao_vira_terca_feira():
    """`bool` é subclasse de `int` em Python: sem o teste explícito, `True`
    passaria por um `isinstance(x, int)` e viraria dia 1."""
    assert ag.normalizar({"dia_semana": True})["dia_semana"] == 0


# ── janela ───────────────────────────────────────────────────────────────────

def test_semanal_olha_a_semana_inteira_e_o_diario_dois_dias():
    """Sem isto quem escolheu semanal receberia só os últimos dois dias e
    perderia o resto — o oposto do que pediu."""
    assert ag.janela_dias({"frequencia": "semanal"}) == 7
    assert ag.janela_dias({"frequencia": "diario"}) == 2
    assert ag.janela_dias(None) == 2
