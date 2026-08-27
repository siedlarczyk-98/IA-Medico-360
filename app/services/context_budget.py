"""
Orçamento de contexto por tokens.

Substitui o corte por caracteres (`msg.content[:800]`, últimas 10 mensagens) que
o orquestrador usava. Aquele corte tinha dois problemas: cortava no meio de uma
frase sem aviso, e não tinha relação nenhuma com o limite real do modelo — dez
mensagens curtas cabiam folgadas, dez mensagens longas estouravam.

**A contagem é uma estimativa, não exata.** Não há tokenizador aqui de
propósito: `tiktoken` só vale para OpenAI, e o projeto fala com quatro
provedores. Um tokenizador por provedor seria dependência pesada para uma
decisão que precisa apenas ser razoável.

**Errar para menos aqui é inofensivo.** O orçamento (6000 tokens) está muito
abaixo da janela de qualquer modelo em uso — 200k no Sonnet. Subestimar em 30%
significa enviar 7800 tokens em vez de 6000: nada estoura. O orçamento é
controle de CUSTO e de ruído, não proteção contra limite técnico. Isso
inverte a intuição comum sobre contagem de tokens, e é o motivo de a razão
abaixo ser calibrada pela mediana e não por um percentil pessimista.
"""

from dataclasses import dataclass

# Razão caracteres/token, medida contra dados reais em 2026-08-27.
#
# Fonte: 54 interações com `tokens_in` gravado, isolando as que não tinham
# histórico, anexo nem busca web somados à contagem (ver docs/debitos.md #3).
# Medianas por modelo:
#
#   claude-sonnet-4-6 (raciocínio clínico)  3.17   ← o que carrega o uso clínico
#   claude-sonnet-4-20250514                4.13
#   gpt-5.4-nano                            4.40
#   global                                  3.55
#   pior caso observado                     2.55
#
# O valor segue a mediana do modelo de raciocínio clínico, arredondada para
# baixo: é ele que recebe os textos longos e densos — evolução, exames, siglas —
# que tokenizam pior. Nos demais a estimativa fica folgada, o que só faz enviar
# um pouco menos de contexto do que caberia.
#
# Antes disto o valor era 3.5, descrito no código como "conservador". Não era:
# 3.5 é a mediana GLOBAL, e uma mediana erra metade das vezes para cada lado —
# a medição mostrou subestimativa em 46% dos casos. O número estava razoável, o
# raciocínio declarado sobre ele é que estava errado.
CHARS_PER_TOKEN = 3.2

# Piso por mensagem: mesmo uma resposta de uma palavra custa a marcação de
# papel e os delimitadores que o provedor acrescenta.
TOKEN_OVERHEAD_POR_MENSAGEM = 4

# Orçamento do histórico, em tokens.
#
# NÃO é limite técnico: a janela do Sonnet é 200k, e 6000 cabe trinta vezes lá
# dentro. É uma decisão de PRODUTO — quanto se aceita pagar, por mensagem, para
# o modelo lembrar da conversa.
#
# Subir aumenta custo e o risco de afogar a pergunta atual em contexto antigo;
# descer faz o médico perceber que "ele esqueceu o que eu disse". Não existe
# valor certo a ser descoberto por medição: existe o valor que o dono do
# produto escolhe. 6000 é um ponto de partida, não uma conclusão.
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
