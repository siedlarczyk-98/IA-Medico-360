"""
Médico 360 — Disjuntor para integrações externas.

O problema que resolve não é a integração CAIR — isso os `try/except` espalhados
pelos serviços já tratam, degradando a resposta com um aviso ao usuário. O
problema é a integração ficar **lenta**: cada requisição espera o timeout inteiro
antes de desistir, segurando conexão e thread. Com o PharmaDB a 15s e várias
consultas simultâneas, uma dependência doente degrada o sistema inteiro.

O disjuntor corta esse custo: depois de N falhas seguidas, para de tentar por um
intervalo e falha na hora. Quando o intervalo passa, deixa UMA requisição testar
o terreno (estado meio-aberto); se ela funcionar, religa.

    fechado ──(N falhas)──> aberto ──(passou o descanso)──> meio-aberto
       ^                                                        │
       └──────────────(1 sucesso)───────────────────────────────┘
                                    │
                       (1 falha) ───┴──> aberto de novo

Escopo é o processo, como os demais caches: com múltiplos workers cada um tem seu
disjuntor. Isso é aceitável — o objetivo é proteger o processo de se esgotar, não
coordenar estado global.
"""

import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class Estado(str, Enum):
    FECHADO = "fechado"        # operação normal
    ABERTO = "aberto"          # falhando rápido, sem tentar
    MEIO_ABERTO = "meio_aberto"  # deixando uma requisição testar


class CircuitoAberto(Exception):
    """Levantada em vez de chamar a integração enquanto o disjuntor está aberto."""

    def __init__(self, nome: str, segundos_restantes: float):
        self.nome = nome
        self.segundos_restantes = segundos_restantes
        super().__init__(
            f"Circuito '{nome}' aberto; nova tentativa em {segundos_restantes:.0f}s"
        )


class Disjuntor:
    """
    Um por integração externa. Não é thread-safe por design: o event loop é
    single-threaded e as transições são idempotentes o bastante para o caso.
    """

    def __init__(
        self,
        nome: str,
        limite_falhas: int = 5,
        descanso_segundos: float = 30.0,
    ):
        self.nome = nome
        self.limite_falhas = limite_falhas
        self.descanso_segundos = descanso_segundos
        self._falhas = 0
        self._estado = Estado.FECHADO
        self._aberto_em: float = 0.0

    # ── Consulta ─────────────────────────────────────────────────────────

    @property
    def estado(self) -> Estado:
        if self._estado is Estado.ABERTO and self._descanso_terminou():
            self._estado = Estado.MEIO_ABERTO
            logger.info("Circuito '%s' em meio-aberto: testando a integração", self.nome)
        return self._estado

    def _descanso_terminou(self) -> bool:
        return (time.monotonic() - self._aberto_em) >= self.descanso_segundos

    def _segundos_restantes(self) -> float:
        return max(0.0, self.descanso_segundos - (time.monotonic() - self._aberto_em))

    # ── Transições ───────────────────────────────────────────────────────

    def registra_sucesso(self) -> None:
        if self._estado is not Estado.FECHADO:
            logger.info("Circuito '%s' fechado: integração respondeu", self.nome)
        self._falhas = 0
        self._estado = Estado.FECHADO

    def registra_falha(self) -> None:
        self._falhas += 1
        # Uma falha em meio-aberto reabre imediatamente: a integração ainda não
        # se recuperou e não vale gastar mais N tentativas para descobrir.
        if self._estado is Estado.MEIO_ABERTO or self._falhas >= self.limite_falhas:
            if self._estado is not Estado.ABERTO:
                logger.warning(
                    "Circuito '%s' ABERTO após %d falha(s); pausando por %.0fs",
                    self.nome, self._falhas, self.descanso_segundos,
                )
            self._estado = Estado.ABERTO
            self._aberto_em = time.monotonic()

    def reset(self) -> None:
        """Volta ao estado inicial. Usado em teste e após intervenção manual."""
        self._falhas = 0
        self._estado = Estado.FECHADO
        self._aberto_em = 0.0

    # ── Uso ──────────────────────────────────────────────────────────────

    async def chama(self, funcao, *args, **kwargs):
        """
        Executa `funcao` sob proteção do disjuntor.

        Levanta `CircuitoAberto` sem chamar nada quando o circuito está aberto —
        o chamador trata isso como qualquer outra falha da integração e devolve
        a degradação que já sabe devolver.
        """
        if self.estado is Estado.ABERTO:
            raise CircuitoAberto(self.nome, self._segundos_restantes())

        try:
            resultado = await funcao(*args, **kwargs)
        except Exception:
            self.registra_falha()
            raise
        else:
            self.registra_sucesso()
            return resultado


# ── Registro por integração ──────────────────────────────────────────────
# Os parâmetros refletem o papel de cada uma: PharmaDB e PubMed enriquecem a
# resposta (degradar é aceitável, então o disjuntor pode ser agressivo);
# Curseduca decide acesso, e abrir o circuito bloqueia login — por isso tolera
# mais falhas e descansa menos.

pharmadb = Disjuntor("pharmadb", limite_falhas=5, descanso_segundos=30)
pubmed = Disjuntor("pubmed", limite_falhas=5, descanso_segundos=30)
curseduca = Disjuntor("curseduca", limite_falhas=10, descanso_segundos=15)

_TODOS = (pharmadb, pubmed, curseduca)


def estado_geral() -> dict[str, str]:
    """Fotografia para o health check e para diagnóstico."""
    return {d.nome: d.estado.value for d in _TODOS}


def reset_todos() -> None:
    for d in _TODOS:
        d.reset()
