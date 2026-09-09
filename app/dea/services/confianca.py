"""
Confiança de um registro de DEA — derivada, e que envelhece sozinha.

Este arquivo existe para substituir um `verified: bool`. O problema do booleano
não é ser simples demais: é não ter eixo de tempo. Um DEA marcado como
verificado em 2026 continua exibindo "verificado" em 2029, mesmo que o aparelho
tenha saído da parede em 2027. Num app onde o custo do erro é alguém correr
300 m até uma parede vazia, isso não serve.

A confiança aqui é **função pura** de fatos observáveis: quantas pessoas
confirmaram, quantas não encontraram, e há quanto tempo foi a última visita.
Pura porque assim é testável sem banco, e porque o decaimento fica definido num
lugar só.

## Por que os limiares vivem em Settings

São chutes calibráveis, não constantes físicas. `news_feed_score_minimo` seguiu
o mesmo caminho (`app/core/config.py`) pelo mesmo motivo: o número certo só
aparece com uso real, e recalibrar não deve exigir migration nem deploy de
schema.

## Por que a API não devolve um número

Um `0.73` vira porcentagem em alguma tela, e porcentagem parece medida. Não é:
é uma heurística sobre quantas pessoas passaram por ali. Devolvemos o rótulo
mais os fatos crus (`confirmacoes`, `dias_desde_ultima_verificacao`), e a
interface diz "confirmado por 3 pessoas · última verificação há 12 dias" — que
é verdade verificável, não estimativa disfarçada.
"""

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta


class NivelConfianca(str, enum.Enum):
    """Ordem decrescente de quanto o registro merece crédito."""

    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"
    # Alguém foi até lá e não encontrou. Não é "pouca informação" — é informação
    # ruim, e precisa aparecer diferente de um registro apenas velho.
    CONTESTADO = "contestado"


@dataclass(frozen=True)
class LimiaresConfianca:
    """Parâmetros do cálculo. Instanciado a partir de `Settings` no router."""

    # Acima disto, nenhuma confirmação sustenta mais o registro sozinha.
    dias_para_expirar: int = 365
    # Abaixo disto, a verificação é considerada recente.
    dias_para_recente: int = 90
    # Confirmações independentes necessárias para o nível mais alto.
    confirmacoes_para_alta: int = 2


@dataclass(frozen=True)
class Confianca:
    nivel: NivelConfianca
    confirmacoes: int
    contestacoes: int
    dias_desde_ultima_verificacao: int | None


def avaliar(
    *,
    verificacoes_positivas: int,
    verificacoes_negativas: int,
    ultima_verificacao_em: datetime | None,
    criado_em: datetime,
    agora: datetime,
    limiares: LimiaresConfianca | None = None,
) -> Confianca:
    """Classifica um dispositivo a partir do seu histórico.

    `agora` é parâmetro em vez de `datetime.now()` interno para o teste poder
    envelhecer o registro sem esperar um ano.
    """
    lim = limiares or LimiaresConfianca()

    referencia = ultima_verificacao_em or criado_em
    dias = max(0, (agora - referencia).days)
    dias_desde_verificacao = max(0, (agora - ultima_verificacao_em).days) if ultima_verificacao_em else None

    # Contestação recente domina qualquer histórico positivo: entre "3 pessoas
    # confirmaram no ano passado" e "alguém não achou ontem", a segunda é a
    # informação que muda a decisão de quem está correndo.
    if verificacoes_negativas > 0 and verificacoes_negativas >= verificacoes_positivas:
        return Confianca(
            nivel=NivelConfianca.CONTESTADO,
            confirmacoes=verificacoes_positivas,
            contestacoes=verificacoes_negativas,
            dias_desde_ultima_verificacao=dias_desde_verificacao,
        )

    # Passado o prazo, o registro deixa de valer por si — não importa quantas
    # confirmações teve. É o envelhecimento que o booleano não tinha.
    if dias > lim.dias_para_expirar:
        nivel = NivelConfianca.BAIXA
    elif verificacoes_positivas >= lim.confirmacoes_para_alta and dias <= lim.dias_para_recente:
        nivel = NivelConfianca.ALTA
    elif verificacoes_positivas > 0:
        nivel = NivelConfianca.MEDIA
    else:
        # Nunca confirmado por ninguém além de quem cadastrou.
        nivel = NivelConfianca.BAIXA

    return Confianca(
        nivel=nivel,
        confirmacoes=verificacoes_positivas,
        contestacoes=verificacoes_negativas,
        dias_desde_ultima_verificacao=dias_desde_verificacao,
    )


def prazo_de_expiracao(limiares: LimiaresConfianca | None = None) -> timedelta:
    """Conveniência para consultas que filtram por idade."""
    lim = limiares or LimiaresConfianca()
    return timedelta(days=lim.dias_para_expirar)
