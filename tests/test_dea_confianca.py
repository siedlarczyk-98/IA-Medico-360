"""
Confiança de um registro de DEA — a lógica que substitui `verified: bool`.

Testes puros: sem banco, sem cliente HTTP. O ponto de tudo aqui é que a
confiança **envelhece**, e envelhecer é justamente o que um booleano não faz.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.dea.services.confianca import (
    Confianca,
    LimiaresConfianca,
    NivelConfianca,
    avaliar,
)

AGORA = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _avaliar(
    *,
    positivas: int = 0,
    negativas: int = 0,
    dias_desde_verificacao: int | None = None,
    dias_desde_criacao: int = 0,
    limiares: LimiaresConfianca | None = None,
) -> Confianca:
    return avaliar(
        verificacoes_positivas=positivas,
        verificacoes_negativas=negativas,
        ultima_verificacao_em=(
            AGORA - timedelta(days=dias_desde_verificacao) if dias_desde_verificacao is not None else None
        ),
        criado_em=AGORA - timedelta(days=dias_desde_criacao),
        agora=AGORA,
        limiares=limiares,
    )


class TestEnvelhecimento:
    """O comportamento que motivou trocar o booleano por um histórico."""

    def test_registro_recem_confirmado_por_duas_pessoas_tem_confianca_alta(self):
        assert _avaliar(positivas=2, dias_desde_verificacao=3).nivel is NivelConfianca.ALTA

    def test_o_MESMO_registro_perde_a_confianca_alta_so_pela_passagem_do_tempo(self):
        # Este é o teste central do módulo: nada mudou no dado além do relógio.
        # Com `verified: bool` o resultado seria idêntico ao do teste acima.
        recente = _avaliar(positivas=2, dias_desde_verificacao=3)
        antigo = _avaliar(positivas=2, dias_desde_verificacao=200)

        assert recente.nivel is NivelConfianca.ALTA
        assert antigo.nivel is NivelConfianca.MEDIA

    def test_apos_o_prazo_de_expiracao_cai_para_baixa_por_mais_confirmacoes_que_tenha(self):
        assert _avaliar(positivas=10, dias_desde_verificacao=400).nivel is NivelConfianca.BAIXA

    def test_registro_nunca_verificado_conta_a_idade_a_partir_do_cadastro(self):
        # Sem verificação, o que envelhece é o cadastro. Um pin de 2 anos que
        # ninguém nunca confirmou não é melhor que um pin de ontem.
        novo = _avaliar(dias_desde_criacao=1)
        velho = _avaliar(dias_desde_criacao=400)

        assert novo.nivel is NivelConfianca.BAIXA
        assert velho.nivel is NivelConfianca.BAIXA
        assert novo.dias_desde_ultima_verificacao is None


class TestContestacao:
    """Quem foi lá e não achou tem peso — e peso maior que histórico antigo."""

    def test_uma_negativa_isolada_contesta_o_registro(self):
        assert _avaliar(negativas=1, dias_desde_verificacao=1).nivel is NivelConfianca.CONTESTADO

    def test_negativa_recente_vence_confirmacoes_antigas(self):
        # "3 pessoas confirmaram no ano passado" vs. "alguém não achou ontem":
        # para quem está correndo, a segunda é a informação que decide.
        resultado = _avaliar(positivas=3, negativas=3, dias_desde_verificacao=1)
        assert resultado.nivel is NivelConfianca.CONTESTADO

    def test_maioria_positiva_nao_e_contestada(self):
        resultado = _avaliar(positivas=5, negativas=1, dias_desde_verificacao=10)
        assert resultado.nivel is NivelConfianca.ALTA
        # A contestação continua visível mesmo sem dominar o rótulo.
        assert resultado.contestacoes == 1


class TestNiveisIntermediarios:
    def test_uma_confirmacao_recente_e_media_nao_alta(self):
        # O limiar padrão exige duas origens independentes: uma pessoa só pode
        # ter se confundido de prédio.
        assert _avaliar(positivas=1, dias_desde_verificacao=2).nivel is NivelConfianca.MEDIA

    def test_limiar_de_confirmacoes_e_configuravel(self):
        limiares = LimiaresConfianca(confirmacoes_para_alta=1)
        assert _avaliar(positivas=1, dias_desde_verificacao=2, limiares=limiares).nivel is NivelConfianca.ALTA

    def test_prazo_de_expiracao_e_configuravel(self):
        limiares = LimiaresConfianca(dias_para_expirar=30)
        assert _avaliar(positivas=2, dias_desde_verificacao=40, limiares=limiares).nivel is NivelConfianca.BAIXA


class TestFatosCrus:
    """A API devolve fatos verificáveis, nunca um score."""

    def test_expoe_contagens_e_idade_em_dias(self):
        resultado = _avaliar(positivas=3, negativas=1, dias_desde_verificacao=12)

        assert resultado.confirmacoes == 3
        assert resultado.contestacoes == 1
        assert resultado.dias_desde_ultima_verificacao == 12

    def test_nao_existe_campo_de_score_numerico(self):
        # Trava deliberada: um número viraria porcentagem em alguma tela, e
        # porcentagem parece medida — não é, é heurística sobre quantas pessoas
        # passaram por ali.
        resultado = _avaliar(positivas=2, dias_desde_verificacao=1)
        campos = set(vars(resultado).keys())

        assert not {"score", "pontuacao", "percentual"} & campos

    @pytest.mark.parametrize("dias", [0, 1, 89, 90, 91, 364, 365, 366])
    def test_nunca_devolve_dias_negativos_nem_explode_nas_bordas(self, dias):
        resultado = _avaliar(positivas=1, dias_desde_verificacao=dias)
        assert resultado.dias_desde_ultima_verificacao == dias
        assert resultado.nivel in set(NivelConfianca)

    def test_verificacao_no_futuro_nao_vira_idade_negativa(self):
        # Relógio de cliente adiantado não deve produzir "-3 dias" na tela.
        resultado = avaliar(
            verificacoes_positivas=1,
            verificacoes_negativas=0,
            ultima_verificacao_em=AGORA + timedelta(days=3),
            criado_em=AGORA,
            agora=AGORA,
        )
        assert resultado.dias_desde_ultima_verificacao == 0
