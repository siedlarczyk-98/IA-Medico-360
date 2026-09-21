"""
Contrato SSE: o backend só emite evento que o frontend conhece.

O chat depende do NOME dos eventos. Um evento novo no backend sem tratamento no
frontend não quebra nada visível — o leitor o repassa, ninguém o trata, e a
informação some em silêncio. O contrato vive em `shared/contrato-sse.ts` e é
conferido nas duas pontas; este é o lado do backend.

Lê o código-fonte como texto, de propósito: exercitar todos os ramos do stream
para colher os nomes custaria uma suíte inteira, e o que se quer aqui é a
invariante estrutural — mesma família do `ROUTE_POLICY`.
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# O contrato é um módulo TypeScript (o chat o importa direto). Aqui é lido como
# texto: uma entrada por linha, `nome: 'papel',`.
CONTRATO = dict(
    re.findall(
        r"^\s*([a-z_]+):\s*'(tratado|informativo)',\s*$",
        (RAIZ / "shared" / "contrato-sse.ts").read_text(encoding="utf-8"),
        re.M,
    )
)
FONTE = (RAIZ / "app" / "services" / "orquestrador_stream_service.py").read_text(encoding="utf-8")


def _emitidos() -> set[str]:
    return set(re.findall(r'_sse\(\s*"([a-z_]+)"', FONTE))


def test_todo_evento_emitido_esta_no_contrato():
    fora = _emitidos() - set(CONTRATO)

    assert not fora, (
        f"O stream emite {sorted(fora)}, que não está em shared/contrato-sse.ts. "
        "Declare lá (e trate no frontend) antes de emitir."
    )


def test_o_contrato_nao_promete_evento_que_ninguem_emite():
    fantasmas = set(CONTRATO) - _emitidos()

    assert not fantasmas, f"No contrato e nunca emitido: {sorted(fantasmas)}"


def test_o_contrato_foi_lido():
    assert CONTRATO.get("token") == "tratado" and len(CONTRATO) >= 5, CONTRATO


def test_a_varredura_enxerga_os_eventos():
    """Se o `_sse(` mudar de forma, a regex para de casar e os testes acima passariam vazios."""
    assert {"start", "token", "text_done", "done", "error"} <= _emitidos()


def test_o_heartbeat_nao_e_evento():
    from app.core.sse import PING

    assert PING.startswith(":"), "comentário SSE: fora do contrato por construção"
