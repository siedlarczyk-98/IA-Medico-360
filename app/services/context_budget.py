"""
Orçamento de contexto por tokens.

Substitui o corte por caracteres (`msg.content[:800]`, últimas 10 mensagens) que
o orquestrador usava. Aquele corte tinha dois problemas: cortava no meio de uma
frase sem aviso, e não tinha relação nenhuma com o limite real do modelo — dez
mensagens curtas cabiam folgadas, dez mensagens longas estouravam.

**A contagem é uma estimativa, não exata.** Não há tokenizador aqui de
propósito: `tiktoken` só vale para OpenAI, e o projeto fala com quatro
provedores. Um tokenizador por provedor seria dependência pesada para uma
decisão que só precisa ser conservadora — o objetivo é não estourar a janela,
e errar para menos é seguro (manda-se menos contexto), errar para mais não é.
"""

from dataclasses import dataclass

# Português técnico com jargão médico e siglas fragmenta mais que inglês comum.
# 3.5 chars/token é conservador de propósito: subestimar a razão superestima a
# contagem, e superestimar a contagem faz cortar contexto a mais — o lado
# seguro do erro.
CHARS_PER_TOKEN = 3.5

# Piso por mensagem: mesmo uma resposta de uma palavra custa a marcação de
# papel e os delimitadores que o provedor acrescenta.
TOKEN_OVERHEAD_POR_MENSAGEM = 4

# Orçamento padrão do histórico, em tokens. Não é o limite do modelo — é quanto
# do prompt aceitamos gastar relembrando a conversa, deixando espaço para o
# prompt de sistema, a pergunta atual e a resposta.
DEFAULT_HISTORY_TOKEN_BUDGET = 6000


@dataclass
class Turn:
    """Uma fala da conversa, já no formato que os providers consomem."""

    role: str  # "user" | "assistant"
    content: str

    def to_message(self) -> dict:
        return {"role": self.role, "content": self.content}


def estimate_tokens(text: str) -> int:
    """Estimativa conservadora do custo em tokens de um texto."""
    if not text:
        return TOKEN_OVERHEAD_POR_MENSAGEM
    return int(len(text) / CHARS_PER_TOKEN) + TOKEN_OVERHEAD_POR_MENSAGEM


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """
    Corta um texto para caber num orçamento, marcando que houve corte.

    A marca importa: sem ela o modelo lê um caso clínico interrompido no meio
    como se fosse o caso inteiro, e pode concluir a partir de dados que na
    verdade existem e não chegaram até ele.
    """
    if max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    marca = " [...trecho anterior omitido por limite de contexto]"
    espaco = int((max_tokens - TOKEN_OVERHEAD_POR_MENSAGEM) * CHARS_PER_TOKEN) - len(marca)
    if espaco <= 0:
        return marca.strip()
    # Mantém o FIM da mensagem: numa evolução clínica, o mais recente costuma
    # ser a conduta e o desfecho, não a identificação do paciente.
    return marca.strip() + " " + text[-espaco:]


def fit_turns_to_budget(
    turns: list[Turn],
    budget_tokens: int = DEFAULT_HISTORY_TOKEN_BUDGET,
) -> list[Turn]:
    """
    Devolve os turnos mais recentes que cabem no orçamento.

    Descarta do mais antigo para o mais recente — numa conversa clínica, o
    turno anterior vale mais que o primeiro. Se o turno mais recente sozinho
    não couber, ele é truncado em vez de descartado: perder a última fala
    esvaziaria o contexto justamente do que mais importa.

    O resultado nunca começa com um turno de assistente. Perplexity e vários
    outros exigem alternância começando por `user`, e um histórico que abre com
    a resposta a uma pergunta ausente é confuso mesmo onde é aceito.
    """
    if not turns or budget_tokens <= 0:
        return []

    selecionados: list[Turn] = []
    restante = budget_tokens

    for turn in reversed(turns):
        custo = estimate_tokens(turn.content)
        if custo <= restante:
            selecionados.append(turn)
            restante -= custo
            continue

        # Não coube. Se ainda não pegamos nada, é o turno mais recente sozinho
        # estourando o orçamento — trunca em vez de sair de mãos vazias.
        if not selecionados:
            cortado = truncate_to_tokens(turn.content, restante)
            if cortado:
                selecionados.append(Turn(role=turn.role, content=cortado))
        break

    selecionados.reverse()

    while selecionados and selecionados[0].role == "assistant":
        selecionados.pop(0)

    if selecionados:
        return selecionados

    # Sobrou nada: o orçamento só dava para a última fala do assistente, que
    # sozinha é inútil (é resposta a uma pergunta que o modelo não vê) e ainda
    # viola a alternância exigida por alguns provedores. Melhor gastar o mesmo
    # orçamento com a última PERGUNTA do médico, que se sustenta sozinha.
    for turn in reversed(turns):
        if turn.role != "user":
            continue
        cortado = truncate_to_tokens(turn.content, budget_tokens)
        return [Turn(role="user", content=cortado)] if cortado else []

    return []


def turns_to_messages(turns: list[Turn]) -> list[dict]:
    """Converte para a lista de dicts que os providers recebem."""
    return [t.to_message() for t in turns]
