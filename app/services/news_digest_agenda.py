"""
Quando o digest de cada médico deve sair.

Separado de `news_digest_service` porque é decisão pura — recebe a preferência e
o instante, devolve sim ou não. Sem banco e sem rede, o que torna possível
testar o calendário inteiro sem subir nada.

AS TRÊS ESCOLHAS DO MÉDICO
- frequência: `diario` ou `semanal`;
- dia da semana: só vale para o semanal (0 = segunda, como `datetime.weekday()`);
- faixa: `manha`, `tarde` ou `noite`.

POR QUE FAIXA E NÃO HORA EXATA
Hora exata obriga a responder "sete da manhã de ONDE", e o sistema não guarda
fuso de usuário nenhum — nem no banco nem vindo do navegador. Com faixas a
pergunta some: a faixa resolve em hora fixa de Brasília, que é onde o público
está. Se um dia houver médico fora do Brasil em número que importe, o caminho é
guardar o fuso junto da preferência e converter aqui — esta função é o único
lugar que precisaria mudar.

O RELÓGIO É UTC
O agendador acorda de hora em hora e compara `agora.hour`; `agora` vem em UTC.
Por isso as faixas viram hora UTC aqui, e não BRT: o processo não sabe nada de
Brasília. Brasília é UTC-3 o ano todo (não há mais horário de verão desde 2019),
então a conta é fixa — se voltar, estas constantes é que mudam.
"""

from datetime import datetime, timedelta

# Faixa -> hora local de Brasília em que o e-mail sai.
HORA_BRT_POR_FAIXA = {
    "manha": 7,
    "tarde": 13,
    "noite": 19,
}

# Brasília é UTC-3 o ano todo desde 2019 (Decreto 9.772/2019 acabou com o
# horário de verão). Se voltar, é esta constante que muda.
OFFSET_BRT = -3

FAIXAS = tuple(HORA_BRT_POR_FAIXA)
FREQUENCIAS = ("diario", "semanal")

# Se a preferência não disser nada, o comportamento é o que já existia antes de
# haver escolha: diário, de manhã. Ninguém passa a receber em horário diferente
# por efeito colateral de um deploy nosso.
PADRAO = {"frequencia": "diario", "dia_semana": 0, "faixa": "manha"}


def hora_utc_da_faixa(faixa: str) -> int:
    """Converte a faixa na hora UTC em que o agendador deve disparar."""
    hora_brt = HORA_BRT_POR_FAIXA.get(faixa, HORA_BRT_POR_FAIXA[PADRAO["faixa"]])
    return (hora_brt - OFFSET_BRT) % 24


def normalizar(bruto: dict | None) -> dict:
    """
    Devolve sempre uma agenda válida, custe o que custar.

    O JSONB aceita qualquer coisa: valor antigo de uma versão anterior, chave
    ausente, tipo errado vindo de um cliente fora do ar. Uma agenda inválida não
    pode virar exceção na rodada — isso derrubaria o digest de TODO MUNDO por
    causa da preferência de uma pessoa. Então tudo que não se reconhece vira o
    padrão.
    """
    bruto = bruto or {}

    frequencia = bruto.get("frequencia")
    if frequencia not in FREQUENCIAS:
        frequencia = PADRAO["frequencia"]

    faixa = bruto.get("faixa")
    if faixa not in FAIXAS:
        faixa = PADRAO["faixa"]

    dia = bruto.get("dia_semana")
    # `bool` é subclasse de `int` em Python: sem este teste, `True` viraria
    # terça-feira em silêncio.
    if not isinstance(dia, int) or isinstance(dia, bool) or not 0 <= dia <= 6:
        dia = PADRAO["dia_semana"]

    return {"frequencia": frequencia, "dia_semana": dia, "faixa": faixa}


def esta_na_hora(agenda: dict | None, agora: datetime) -> bool:
    """
    É agora que este médico recebe?

    `agora` vem em UTC e com hora cheia de granularidade — o agendador acorda de
    hora em hora, então comparar a hora é o máximo de precisão que existe. Pedir
    mais preciso exigiria acordar mais vezes, o que não se paga para um e-mail.
    """
    a = normalizar(agenda)

    if agora.hour != hora_utc_da_faixa(a["faixa"]):
        return False

    if a["frequencia"] == "diario":
        return True

    # Semanal: o dia escolhido é em horário de BRASÍLIA, não UTC. Para as faixas
    # da tarde e da noite isso não muda nada, mas a da manhã (7h BRT = 10h UTC)
    # cai no mesmo dia; já uma faixa que cruzasse a meia-noite mudaria o dia da
    # semana. Converter antes de comparar deixa a regra certa para qualquer
    # faixa que venha a existir.
    local = agora + timedelta(hours=OFFSET_BRT)
    return local.weekday() == a["dia_semana"]


def janela_dias(agenda: dict | None) -> int:
    """
    Quantos dias o digest olha para trás.

    O diário cobre 2 dias (a janela que já existia, com folga para uma rodada
    perdida). O semanal precisa cobrir a semana inteira, senão a pessoa que
    escolheu semanal receberia só o que saiu nos últimos dois dias e perderia o
    resto — o oposto do que ela pediu.
    """
    return 7 if normalizar(agenda)["frequencia"] == "semanal" else 2
